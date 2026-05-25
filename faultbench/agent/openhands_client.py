"""OpenHands agent integration for FaultBench.

Communicates with a running OpenHands server via its v0 REST API to:
1. Start a new app-conversation (creates a start-task)
2. Poll the start-task until the conversation is READY
3. Poll conversation events for terminal execution state
4. Extract execution results (success, iterations, tokens, raw log)

OpenHands v0 REST API (discovered from /openapi.json at the live server):
  POST   /api/v1/app-conversations                              → AppConversationStartTask
  GET    /api/v1/app-conversations/start-tasks/search           → poll start-task
  GET    /api/v1/conversation/{id}/events/search                → poll execution state
  GET    /api/v1/app-conversations?id__eq={id}                  → get conversation + metrics
  DELETE /api/v1/app-conversations/{id}                         → cleanup
  GET    /health                                                 → liveness
  GET    /alive                                                  → liveness

ConversationExecutionStatus enum:
  idle | running | paused | waiting_for_confirmation |
  finished | error | stuck | deleting

AppConversationStartTaskStatus enum:
  WORKING | WAITING_FOR_SANDBOX | PREPARING_REPOSITORY |
  RUNNING_SETUP_SCRIPT | SETTING_UP_GIT_HOOKS | SETTING_UP_SKILLS |
  STARTING_CONVERSATION | READY | ERROR
"""

from __future__ import annotations

import os
import time
from typing import Any, Optional

import httpx

from faultbench.agent.base import AgentExecutionError, AgentResult, BaseAgent
from faultbench.logging import get_logger

log = get_logger(__name__)

# Terminal states for AppConversationStartTask
_START_TASK_TERMINAL = {"READY", "ERROR"}

# Terminal states for ConversationExecutionStatus
_EXEC_TERMINAL = {"idle", "finished", "error", "stuck"}

# States that mean the agent completed successfully
_EXEC_SUCCESS = {"finished"}

# States that mean the agent is waiting for human (treat as timeout/failure)
_EXEC_WAITING = {"waiting_for_confirmation", "paused"}


class OpenHandsClient(BaseAgent):
    """Concrete agent implementation for OpenHands (v0 REST API).

    Connects to a locally running OpenHands server and submits coding
    tasks via the ``/api/v1/app-conversations`` endpoint.

    Configuration is sourced from (in order of precedence):
      1. Constructor arguments
      2. Environment variables: ``OPENHANDS_BASE_URL``, ``OPENHANDS_HOST``,
         ``OPENHANDS_PORT``

    The client does NOT require an API key for local self-hosted deployments.
    """

    def __init__(
        self,
        *,
        base_url: Optional[str] = None,
        host: Optional[str] = None,
        port: Optional[int] = None,
        model: str = "claude-sonnet-4-20250514",
        poll_interval: float = 5.0,
        start_task_timeout: float = 120.0,
    ) -> None:
        # Resolve base URL: explicit > env OPENHANDS_BASE_URL > host:port combo
        if base_url:
            self._base_url = base_url.rstrip("/")
        elif env_url := os.environ.get("OPENHANDS_BASE_URL"):
            self._base_url = env_url.rstrip("/")
        else:
            _host = host or os.environ.get("OPENHANDS_HOST", "http://localhost")
            _port = port or int(os.environ.get("OPENHANDS_PORT", "3000"))
            self._base_url = f"{_host.rstrip('/')}:{_port}"

        self._model = model
        self._poll_interval = poll_interval
        # How long to wait for the sandbox / runtime to start before execution
        self._start_task_timeout = start_task_timeout

    # ---------------------------------------------------------------------- #
    # BaseAgent interface                                                     #
    # ---------------------------------------------------------------------- #

    @property
    def agent_name(self) -> str:
        return "openhands"

    def is_available(self) -> bool:
        """Check if the OpenHands server is reachable via /health."""
        try:
            response = httpx.get(
                f"{self._base_url}/health",
                timeout=10.0,
            )
            # /health returns 200 with body "OK"
            available = response.status_code == 200
            log.info(
                "openhands_health_check",
                available=available,
                url=self._base_url,
                status=response.status_code,
            )
            return available
        except (httpx.ConnectError, httpx.TimeoutException) as exc:
            log.warning("openhands_unreachable", url=self._base_url, error=str(exc))
            return False

    def execute_task(
        self,
        *,
        instruction: str,
        workspace_dir: str,
        max_iterations: int,
        timeout_seconds: int,
    ) -> AgentResult:
        """Submit a task to OpenHands and poll until completion.

        Full flow:
          1. POST /api/v1/app-conversations       — create conversation + start sandbox
          2. Poll start-task until READY or ERROR
          3. Poll ConversationStateUpdateEvent until terminal execution state
          4. Fetch all events for raw output + trace
          5. Delete conversation (best-effort cleanup)

        Args:
            instruction: The coding task instruction (natural language).
            workspace_dir: Path to the workspace directory on the host.
                           NOTE: OpenHands must be able to mount this path.
                           Pass absolute paths accessible to the OpenHands process.
            max_iterations: Maximum agent iterations (passed as system hint).
            timeout_seconds: Hard timeout for the entire execution.

        Returns:
            AgentResult with execution details.

        Raises:
            AgentExecutionError: On unrecoverable communication failure.
        """
        log.info(
            "openhands_task_start",
            workspace=workspace_dir,
            model=self._model,
            max_iterations=max_iterations,
            timeout=timeout_seconds,
        )

        start_time = time.time()
        conversation_id: Optional[str] = None

        try:
            # ── Step 1: Create conversation ──────────────────────────────────
            start_task_id, conversation_id = self._start_conversation(
                instruction=instruction,
                workspace_dir=workspace_dir,
                max_iterations=max_iterations,
            )

            # ── Step 2: Poll start-task until sandbox is READY ───────────────
            ready_conversation_id = self._poll_start_task(
                start_task_id=start_task_id,
                timeout_seconds=self._start_task_timeout,
                start_time=time.time(),  # separate clock for sandbox init
            )
            # Use the conversation_id from the start-task poll if we didn't
            # get it in the initial response (it may have been <pending>).
            if ready_conversation_id:
                conversation_id = ready_conversation_id

            if not conversation_id:
                raise AgentExecutionError(
                    f"OpenHands start-task {start_task_id} completed but "
                    "returned no conversation_id"
                )

            # ── Step 3: Poll execution until terminal state ──────────────────
            final_exec_status = self._poll_execution(
                conversation_id=conversation_id,
                timeout_seconds=timeout_seconds,
                global_start=start_time,
            )

            elapsed = time.time() - start_time

            # ── Step 4: Extract results ──────────────────────────────────────
            result = self._extract_result(
                conversation_id=conversation_id,
                final_exec_status=final_exec_status,
                elapsed=elapsed,
            )

            log.info(
                "openhands_task_complete",
                conversation_id=conversation_id,
                success=result.success,
                iterations=result.iterations_used,
                elapsed_seconds=round(elapsed, 2),
                exec_status=final_exec_status,
            )
            return result

        except AgentExecutionError:
            raise
        except Exception as exc:
            elapsed = time.time() - start_time
            log.exception(
                "openhands_task_failed",
                elapsed_seconds=round(elapsed, 2),
                error=str(exc),
            )
            return AgentResult(
                success=False,
                iterations_used=0,
                tokens_used=None,
                raw_output=f"OpenHands execution failed: {exc}",
                error_message=str(exc),
            )
        finally:
            # ── Step 5: Best-effort cleanup ──────────────────────────────────
            if conversation_id:
                self._delete_conversation(conversation_id)

    # ---------------------------------------------------------------------- #
    # Internal API methods                                                    #
    # ---------------------------------------------------------------------- #

    def _start_conversation(
        self,
        *,
        instruction: str,
        workspace_dir: str,
        max_iterations: int,
    ) -> tuple[str, str]:
        """POST /api/v1/app-conversations to create a new conversation.

        Args:
            instruction: Natural language task instruction.
            workspace_dir: Host path for the workspace.
            max_iterations: Passed as a system message hint.

        Returns:
            Tuple of (start_task_id, conversation_id).
            ``conversation_id`` may be empty string until the start-task
            completes — check the polled start-task for the final ID.

        Raises:
            AgentExecutionError: On API failure.
        """
        log.info("openhands_starting_conversation", workspace=workspace_dir)

        # Build the system message suffix with workspace context
        system_suffix = (
            f"The workspace is located at: {workspace_dir}. "
            f"Work exclusively within that directory. "
            f"Maximum iterations: {max_iterations}."
        )

        payload: dict[str, Any] = {
            "initial_message": {
                "role": "user",
                "content": [{"type": "text", "text": instruction}],
                "run": True,
            },
            "system_message_suffix": system_suffix,
            "llm_model": self._model,
        }

        try:
            response = httpx.post(
                f"{self._base_url}/api/v1/app-conversations",
                json=payload,
                timeout=30.0,
            )
        except (httpx.ConnectError, httpx.TimeoutException) as exc:
            raise AgentExecutionError(
                f"Cannot reach OpenHands at {self._base_url}: {exc}"
            ) from exc

        if response.status_code not in (200, 201):
            raise AgentExecutionError(
                f"Failed to start conversation: HTTP {response.status_code} "
                f"— {response.text[:500]}"
            )

        data = response.json()
        start_task_id = data.get("id", "")
        conversation_id = data.get("app_conversation_id") or ""

        if not start_task_id:
            raise AgentExecutionError(
                f"OpenHands response missing start-task id: {data}"
            )

        log.info(
            "openhands_conversation_starting",
            start_task_id=start_task_id,
            initial_conversation_id=conversation_id or "<pending>",
        )
        return start_task_id, conversation_id

    def _poll_start_task(
        self,
        *,
        start_task_id: str,
        timeout_seconds: float,
        start_time: float,
    ) -> str:
        """Poll start-task until READY or ERROR.

        Returns:
            The ``app_conversation_id`` once READY.

        Raises:
            AgentExecutionError: If start-task errors or times out.
        """
        log.info("openhands_polling_start_task", start_task_id=start_task_id)

        while True:
            elapsed = time.time() - start_time
            if elapsed > timeout_seconds:
                raise AgentExecutionError(
                    f"Timed out waiting for sandbox to start "
                    f"(start_task={start_task_id}, elapsed={elapsed:.1f}s)"
                )

            try:
                response = httpx.get(
                    f"{self._base_url}/api/v1/app-conversations/start-tasks/search",
                    params={"conversation_id__eq": start_task_id},
                    timeout=15.0,
                )
                if response.status_code == 200:
                    data = response.json()
                    items = data.get("items", [])
                    if items:
                        task = items[0]
                        status = task.get("status", "UNKNOWN")
                        conv_id = task.get("app_conversation_id") or ""

                        log.debug(
                            "openhands_start_task_poll",
                            start_task_id=start_task_id,
                            status=status,
                            elapsed=round(elapsed, 1),
                        )

                        if status == "READY":
                            log.info(
                                "openhands_start_task_ready",
                                start_task_id=start_task_id,
                                conversation_id=conv_id,
                            )
                            return conv_id

                        if status == "ERROR":
                            detail = task.get("detail", "unknown error")
                            raise AgentExecutionError(
                                f"OpenHands start-task failed: {detail}"
                            )
                else:
                    log.warning(
                        "openhands_start_task_poll_error",
                        status_code=response.status_code,
                    )

            except AgentExecutionError:
                raise
            except (httpx.ConnectError, httpx.TimeoutException) as exc:
                log.warning("openhands_start_task_poll_conn_error", error=str(exc))

            time.sleep(self._poll_interval)

    def _poll_execution(
        self,
        *,
        conversation_id: str,
        timeout_seconds: int,
        global_start: float,
    ) -> str:
        """Poll ConversationStateUpdateEvent until a terminal execution status.

        Queries ``/api/v1/conversation/{id}/events/search`` filtering for
        ``ConversationStateUpdateEvent`` events and tracking the most recent
        ``execution_status`` value.

        Args:
            conversation_id: The conversation to monitor.
            timeout_seconds: Hard timeout from the global benchmark start.
            global_start: Time when the benchmark run started.

        Returns:
            The final ``ConversationExecutionStatus`` string.
        """
        log.info(
            "openhands_polling_execution",
            conversation_id=conversation_id,
        )

        # Track event cursor to avoid reprocessing
        last_event_id: Optional[str] = None
        current_status = "running"

        while True:
            elapsed = time.time() - global_start
            if elapsed > timeout_seconds:
                log.warning(
                    "openhands_execution_timeout",
                    conversation_id=conversation_id,
                    elapsed=round(elapsed, 1),
                    timeout=timeout_seconds,
                )
                return "timeout"

            # Also return early if stuck in a state that requires human input
            if current_status in _EXEC_WAITING:
                log.warning(
                    "openhands_execution_waiting",
                    conversation_id=conversation_id,
                    status=current_status,
                )
                return current_status

            try:
                params: dict[str, Any] = {
                    "kind__eq": "ConversationStateUpdateEvent",
                    "limit": 50,
                }
                if last_event_id:
                    params["page_id"] = last_event_id

                response = httpx.get(
                    f"{self._base_url}/api/v1/conversation/{conversation_id}/events/search",
                    params=params,
                    timeout=15.0,
                )

                if response.status_code == 200:
                    ct = response.headers.get("content-type", "")
                    if "application/json" not in ct:
                        log.warning(
                            "openhands_events_non_json_response",
                            conversation_id=conversation_id,
                            content_type=ct,
                            body_preview=response.text[:200],
                        )
                        time.sleep(self._poll_interval)
                        continue
                    data = response.json()

                    items: list[dict[str, Any]] = data.get("items", [])

                    for event in items:
                        last_event_id = event.get("id", last_event_id)
                        value = event.get("value", {})
                        if isinstance(value, dict):
                            exec_status = value.get("execution_status")
                            if exec_status:
                                current_status = exec_status
                                log.debug(
                                    "openhands_exec_status_update",
                                    conversation_id=conversation_id,
                                    status=exec_status,
                                    elapsed=round(elapsed, 1),
                                )

                    if current_status in _EXEC_TERMINAL:
                        log.info(
                            "openhands_execution_terminal",
                            conversation_id=conversation_id,
                            final_status=current_status,
                            elapsed=round(elapsed, 1),
                        )
                        return current_status

                elif response.status_code == 404:
                    log.warning(
                        "openhands_conversation_not_found",
                        conversation_id=conversation_id,
                    )
                    return "error"
                else:
                    log.warning(
                        "openhands_poll_error",
                        conversation_id=conversation_id,
                        status_code=response.status_code,
                    )

            except (httpx.ConnectError, httpx.TimeoutException) as exc:
                log.warning(
                    "openhands_poll_conn_error",
                    conversation_id=conversation_id,
                    error=str(exc),
                )

            time.sleep(self._poll_interval)

    def _extract_result(
        self,
        *,
        conversation_id: str,
        final_exec_status: str,
        elapsed: float,
    ) -> AgentResult:
        """Build AgentResult from conversation state, events, and metrics.

        Args:
            conversation_id: The completed conversation.
            final_exec_status: The terminal execution status string.
            elapsed: Total elapsed time in seconds.

        Returns:
            A fully populated AgentResult.
        """
        success = final_exec_status in _EXEC_SUCCESS

        # Fetch conversation metadata for metrics
        iterations_used = 0
        tokens_used: Optional[int] = None
        try:
            resp = httpx.get(
                f"{self._base_url}/api/v1/app-conversations",
                params={"ids": [conversation_id]},
                timeout=15.0,
            )
            if resp.status_code == 200 and "application/json" in resp.headers.get("content-type", ""):
                items = resp.json().get("items", [])
                if items:
                    conv = items[0]
                    metrics = conv.get("metrics") or {}
                    tokens_used = metrics.get("accumulated_token_usage", {}).get(
                        "total_tokens"
                    )
                    # iterations ≈ number of LLM calls
                    iterations_used = metrics.get("accumulated_token_usage", {}).get(
                        "num_requests", 0
                    ) or 0
        except Exception as exc:
            log.warning("openhands_metrics_fetch_error", error=str(exc))

        # Fetch events for raw output + trace
        raw_output = self._fetch_all_events_text(conversation_id)
        trace = self._build_trace(conversation_id)

        error_message: Optional[str] = None
        if final_exec_status == "timeout":
            error_message = f"Execution timed out after {elapsed:.1f}s"
        elif final_exec_status in ("error", "stuck"):
            error_message = f"Execution ended with status '{final_exec_status}'"
        elif final_exec_status in _EXEC_WAITING:
            error_message = (
                f"Execution halted waiting for confirmation (status='{final_exec_status}')"
            )

        return AgentResult(
            success=success,
            iterations_used=iterations_used,
            tokens_used=tokens_used,
            raw_output=raw_output,
            error_message=error_message,
            execution_trace=trace,
        )

    def _fetch_all_events_text(self, conversation_id: str) -> str:
        """Fetch all events from a conversation and return them as raw text."""
        try:
            response = httpx.get(
                f"{self._base_url}/api/v1/conversation/{conversation_id}/events/search",
                params={"limit": 200},
                timeout=30.0,
            )
            if response.status_code == 200:
                events = response.json().get("items", [])
                parts: list[str] = []
                for event in events:
                    kind = event.get("kind", "unknown")
                    value = event.get("value", {})
                    ts = event.get("timestamp", "")
                    if isinstance(value, dict):
                        content = str(value)[:500]
                    else:
                        content = str(value)[:500]
                    parts.append(f"[{ts}] [{kind}] {content}")
                return "\n".join(parts)
            return f"[Could not fetch events: HTTP {response.status_code}]"
        except Exception as exc:
            return f"[Could not fetch events: {exc}]"

    def _build_trace(self, conversation_id: str) -> list[dict[str, str]]:
        """Build a simplified execution trace from conversation events."""
        trace: list[dict[str, str]] = []
        try:
            response = httpx.get(
                f"{self._base_url}/api/v1/conversation/{conversation_id}/events/search",
                params={"kind__eq": "ActionEvent", "limit": 100},
                timeout=30.0,
            )
            if response.status_code == 200:
                events = response.json().get("items", [])
                for i, event in enumerate(events):
                    value = event.get("value", {})
                    if isinstance(value, dict):
                        action_type = value.get("action", value.get("type", "unknown"))
                        output = str(value.get("content", value.get("output", "")))[:500]
                    else:
                        action_type = "unknown"
                        output = str(value)[:200]
                    trace.append({
                        "step": str(i + 1),
                        "action": action_type,
                        "status": event.get("source", "unknown"),
                        "content": output,
                    })
        except Exception as exc:
            log.warning("openhands_trace_fetch_error", error=str(exc))
        return trace

    def _delete_conversation(self, conversation_id: str) -> None:
        """Delete a conversation (best-effort cleanup). Errors are suppressed."""
        try:
            httpx.delete(
                f"{self._base_url}/api/v1/app-conversations/{conversation_id}",
                timeout=10.0,
            )
            log.info("openhands_conversation_deleted", conversation_id=conversation_id)
        except Exception as exc:
            log.warning(
                "openhands_conversation_delete_failed",
                conversation_id=conversation_id,
                error=str(exc),
            )
