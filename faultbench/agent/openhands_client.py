"""OpenHands agent integration for FaultBench.

Communicates with a running OpenHands server via its REST API to:
1. Create a new task/conversation
2. Submit the coding instruction
3. Poll for completion
4. Extract execution results (success, iterations, tokens)

OpenHands API docs: https://docs.all-hands.dev/
"""

from __future__ import annotations

import os
import time
from typing import Any, Optional

import httpx

from faultbench.agent.base import AgentExecutionError, AgentResult, BaseAgent
from faultbench.logging import get_logger

log = get_logger(__name__)


class OpenHandsClient(BaseAgent):
    """Concrete agent implementation for OpenHands.

    Connects to a running OpenHands server and submits coding tasks
    via the REST API.

    Configuration is sourced from:
    - Environment: ``OPENHANDS_HOST``, ``OPENHANDS_PORT``, ``ANTHROPIC_API_KEY``
    - Constructor arguments (override env)
    """

    def __init__(
        self,
        *,
        host: Optional[str] = None,
        port: Optional[int] = None,
        api_key: Optional[str] = None,
        model: str = "claude-sonnet-4-20250514",
        poll_interval: float = 5.0,
    ) -> None:
        self._host = host or os.environ.get("OPENHANDS_HOST", "http://localhost")
        self._port = port or int(os.environ.get("OPENHANDS_PORT", "3000"))
        self._api_key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")
        self._model = model
        self._poll_interval = poll_interval
        self._base_url = f"{self._host}:{self._port}"

    @property
    def agent_name(self) -> str:
        return "openhands"

    def is_available(self) -> bool:
        """Check if the OpenHands server is reachable."""
        try:
            response = httpx.get(
                f"{self._base_url}/api/health",
                timeout=10.0,
            )
            available = response.status_code == 200
            log.info("openhands_health_check", available=available, url=self._base_url)
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

        The full flow:
        1. POST /api/conversations — create a new conversation
        2. POST /api/conversations/{id}/messages — submit instruction
        3. GET /api/conversations/{id}/state — poll until finished
        4. GET /api/conversations/{id}/messages — extract results

        Args:
            instruction: The coding task instruction.
            workspace_dir: Path to the workspace directory.
            max_iterations: Maximum agent iterations.
            timeout_seconds: Hard timeout for the entire execution.

        Returns:
            AgentResult with execution details.

        Raises:
            AgentExecutionError: On communication or execution failure.
        """
        if not self._api_key:
            raise AgentExecutionError(
                "ANTHROPIC_API_KEY is not set. Cannot execute OpenHands task."
            )

        log.info(
            "openhands_task_start",
            workspace=workspace_dir,
            model=self._model,
            max_iterations=max_iterations,
            timeout=timeout_seconds,
        )

        start_time = time.time()

        try:
            # Step 1: Create conversation
            conversation_id = self._create_conversation(workspace_dir)

            # Step 2: Submit instruction
            self._submit_instruction(conversation_id, instruction, max_iterations)

            # Step 3: Poll for completion
            final_state = self._poll_completion(
                conversation_id, timeout_seconds, start_time
            )

            # Step 4: Extract results
            result = self._extract_result(
                conversation_id, final_state, start_time
            )

            elapsed = time.time() - start_time
            log.info(
                "openhands_task_complete",
                conversation_id=conversation_id,
                success=result.success,
                iterations=result.iterations_used,
                elapsed_seconds=round(elapsed, 2),
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

    def _create_conversation(self, workspace_dir: str) -> str:
        """Create a new OpenHands conversation.

        Returns:
            The conversation ID.
        """
        log.info("openhands_creating_conversation", workspace=workspace_dir)

        response = httpx.post(
            f"{self._base_url}/api/conversations",
            json={
                "workspace_dir": workspace_dir,
                "model": self._model,
                "api_key": self._api_key,
            },
            timeout=30.0,
        )

        if response.status_code not in (200, 201):
            raise AgentExecutionError(
                f"Failed to create conversation: {response.status_code} {response.text}"
            )

        data = response.json()
        conversation_id = data.get("conversation_id", data.get("id", ""))
        if not conversation_id:
            raise AgentExecutionError(
                f"No conversation_id in response: {data}"
            )

        log.info("openhands_conversation_created", conversation_id=conversation_id)
        return conversation_id

    def _submit_instruction(
        self, conversation_id: str, instruction: str, max_iterations: int
    ) -> None:
        """Submit the coding instruction to an existing conversation."""
        log.info(
            "openhands_submitting_instruction",
            conversation_id=conversation_id,
            instruction_length=len(instruction),
        )

        response = httpx.post(
            f"{self._base_url}/api/conversations/{conversation_id}/messages",
            json={
                "role": "user",
                "content": instruction,
                "max_iterations": max_iterations,
            },
            timeout=30.0,
        )

        if response.status_code not in (200, 201):
            raise AgentExecutionError(
                f"Failed to submit instruction: {response.status_code} {response.text}"
            )

        log.info("openhands_instruction_submitted", conversation_id=conversation_id)

    def _poll_completion(
        self,
        conversation_id: str,
        timeout_seconds: int,
        start_time: float,
    ) -> dict[str, Any]:
        """Poll the conversation state until it completes or times out.

        Returns:
            The final state dictionary.
        """
        terminal_states = {"finished", "error", "stopped", "cancelled"}

        while True:
            elapsed = time.time() - start_time
            if elapsed > timeout_seconds:
                log.warning(
                    "openhands_timeout",
                    conversation_id=conversation_id,
                    elapsed=round(elapsed, 2),
                    timeout=timeout_seconds,
                )
                return {"state": "timeout", "elapsed": elapsed}

            try:
                response = httpx.get(
                    f"{self._base_url}/api/conversations/{conversation_id}/state",
                    timeout=15.0,
                )

                if response.status_code == 200:
                    state_data = response.json()
                    current_state = state_data.get("state", "unknown")

                    log.debug(
                        "openhands_poll",
                        conversation_id=conversation_id,
                        state=current_state,
                        elapsed=round(elapsed, 2),
                    )

                    if current_state in terminal_states:
                        return state_data
                else:
                    log.warning(
                        "openhands_poll_error",
                        conversation_id=conversation_id,
                        status_code=response.status_code,
                    )

            except (httpx.ConnectError, httpx.TimeoutException) as exc:
                log.warning(
                    "openhands_poll_connection_error",
                    conversation_id=conversation_id,
                    error=str(exc),
                )

            time.sleep(self._poll_interval)

    def _extract_result(
        self,
        conversation_id: str,
        final_state: dict[str, Any],
        start_time: float,
    ) -> AgentResult:
        """Extract execution results from the final conversation state.

        Fetches messages, computes metrics, and builds an AgentResult.
        """
        elapsed = time.time() - start_time
        state_value = final_state.get("state", "unknown")

        # Determine success
        success = state_value == "finished"

        # Extract iteration count
        iterations = final_state.get("iterations", 0)
        if iterations == 0:
            iterations = final_state.get("num_steps", 0)

        # Extract token usage
        tokens_used = final_state.get("tokens_used")
        if tokens_used is None:
            metrics = final_state.get("metrics", {})
            tokens_used = metrics.get("total_tokens")

        # Fetch messages for raw output
        raw_output = self._fetch_messages(conversation_id)

        # Build execution trace
        trace = self._build_trace(final_state)

        error_message = None
        if state_value == "error":
            error_message = final_state.get("error", "Unknown error")
        elif state_value == "timeout":
            error_message = f"Execution timed out after {elapsed:.1f}s"

        return AgentResult(
            success=success,
            iterations_used=iterations,
            tokens_used=tokens_used,
            raw_output=raw_output,
            error_message=error_message,
            execution_trace=trace,
        )

    def _fetch_messages(self, conversation_id: str) -> str:
        """Fetch all messages from a conversation as raw text."""
        try:
            response = httpx.get(
                f"{self._base_url}/api/conversations/{conversation_id}/messages",
                timeout=30.0,
            )
            if response.status_code == 200:
                messages = response.json()
                parts: list[str] = []
                if isinstance(messages, list):
                    for msg in messages:
                        role = msg.get("role", "unknown")
                        content = msg.get("content", "")
                        parts.append(f"[{role}] {content}")
                return "\n\n".join(parts)
            return f"[Could not fetch messages: HTTP {response.status_code}]"
        except Exception as exc:
            return f"[Could not fetch messages: {exc}]"

    def _build_trace(self, state_data: dict[str, Any]) -> list[dict[str, str]]:
        """Build a simplified execution trace from state data."""
        trace: list[dict[str, str]] = []
        steps = state_data.get("steps", state_data.get("history", []))

        if isinstance(steps, list):
            for i, step in enumerate(steps):
                if isinstance(step, dict):
                    trace.append({
                        "step": str(i + 1),
                        "action": step.get("action", step.get("type", "unknown")),
                        "status": step.get("status", step.get("result", "unknown")),
                        "content": str(step.get("content", step.get("output", "")))[:500],
                    })

        return trace
