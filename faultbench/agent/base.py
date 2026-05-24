"""Abstract interface for coding agent integrations.

All agent implementations (OpenHands, future agents) must implement
the :class:`BaseAgent` interface.  This ensures the orchestration
layer can work with any agent without knowing its internals.
"""

from __future__ import annotations

import abc
import dataclasses
from typing import Optional


@dataclasses.dataclass(frozen=True)
class AgentResult:
    """Result returned by an agent after executing a task.

    This is the standard contract between the agent layer and the
    metrics/orchestration layers.
    """

    success: bool
    iterations_used: int  # maps to retry_count in RunRecord
    tokens_used: Optional[int]
    raw_output: str  # full agent output/logs
    error_message: Optional[str] = None
    execution_trace: Optional[list[dict[str, str]]] = None  # step-by-step trace


class BaseAgent(abc.ABC):
    """Abstract interface for autonomous coding agents.

    Concrete implementations handle the specifics of communicating with
    a particular agent platform (e.g., OpenHands REST API).
    """

    @property
    @abc.abstractmethod
    def agent_name(self) -> str:
        """Return the canonical name of this agent (e.g., 'openhands')."""

    @abc.abstractmethod
    def execute_task(
        self,
        *,
        instruction: str,
        workspace_dir: str,
        max_iterations: int,
        timeout_seconds: int,
    ) -> AgentResult:
        """Execute a coding task and return the result.

        Args:
            instruction: Natural language task description for the agent.
            workspace_dir: Path to the workspace the agent should operate on.
            max_iterations: Maximum number of agent iterations/steps.
            timeout_seconds: Hard timeout for the entire execution.

        Returns:
            An :class:`AgentResult` with execution details.

        Raises:
            AgentExecutionError: If the agent fails to execute.
        """

    @abc.abstractmethod
    def is_available(self) -> bool:
        """Check if the agent is ready to accept tasks.

        Returns:
            ``True`` if the agent is reachable and operational.
        """


class AgentExecutionError(Exception):
    """Raised when an agent fails to execute a task."""
