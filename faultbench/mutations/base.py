"""Abstract base class for all FaultBench mutation implementations.

Every concrete mutation (schema drift, dependency drift, etc.) inherits from
``BaseMutation`` and implements the three abstract methods: ``apply``,
``rollback``, and ``validate``.  The public entry-points wrap those methods
with structured logging so that every mutation is traced consistently.
"""

from __future__ import annotations

import abc
from pathlib import Path

from faultbench.constants import MutationType
from faultbench.logging import get_logger
from faultbench.models import MutationSpec

log = get_logger(__name__)


class BaseMutation(abc.ABC):
    """Base class for all mutation implementations.

    Subclasses MUST set ``mutation_type`` to the appropriate
    :class:`~faultbench.constants.MutationType` member and implement
    ``apply``, ``rollback``, and ``validate``.
    """

    # ------------------------------------------------------------------ #
    # Abstract interface                                                  #
    # ------------------------------------------------------------------ #

    @property
    @abc.abstractmethod
    def mutation_type(self) -> MutationType:
        """Return the :class:`MutationType` this class handles."""

    @abc.abstractmethod
    def apply(self, task_dir: Path, spec: MutationSpec) -> None:
        """Apply the mutation to *task_dir* according to *spec*.

        Must be deterministic and idempotent when called with the same
        arguments.

        Raises:
            FileNotFoundError: if a required file is missing.
            PermissionError: if a file cannot be written.
            ValueError: if *spec* contains invalid parameters.
        """

    @abc.abstractmethod
    def rollback(self, task_dir: Path, spec: MutationSpec) -> None:
        """Undo every change made by :meth:`apply`.

        The rollback uses ``spec.rollback_actions`` to reverse the mutation.
        After rollback, the task directory MUST be identical to its state
        before ``apply`` was called.
        """

    @abc.abstractmethod
    def validate(self, task_dir: Path, spec: MutationSpec) -> bool:
        """Check that all preconditions for *spec* hold in *task_dir*.

        Returns ``True`` when the mutation can safely be applied, ``False``
        otherwise.  Must not modify the file-system.
        """

    # ------------------------------------------------------------------ #
    # Logged public helpers (template-method wrappers)                    #
    # ------------------------------------------------------------------ #

    def safe_apply(self, task_dir: Path, spec: MutationSpec) -> None:
        """Validate, then apply the mutation with structured logging."""
        bound = log.bind(
            mutation_type=str(self.mutation_type),
            task_dir=str(task_dir),
        )
        bound.info("mutation_apply_started")

        try:
            if not self.validate(task_dir, spec):
                bound.error("mutation_validation_failed")
                raise ValueError(
                    f"Precondition check failed for {self.mutation_type} "
                    f"in {task_dir}"
                )
            self.apply(task_dir, spec)
            bound.info("mutation_apply_succeeded")
        except Exception:
            bound.exception("mutation_apply_failed")
            raise

    def safe_rollback(self, task_dir: Path, spec: MutationSpec) -> None:
        """Rollback the mutation with structured logging."""
        bound = log.bind(
            mutation_type=str(self.mutation_type),
            task_dir=str(task_dir),
        )
        bound.info("mutation_rollback_started")

        try:
            self.rollback(task_dir, spec)
            bound.info("mutation_rollback_succeeded")
        except Exception:
            bound.exception("mutation_rollback_failed")
            raise

    def safe_validate(self, task_dir: Path, spec: MutationSpec) -> bool:
        """Validate preconditions with structured logging."""
        bound = log.bind(
            mutation_type=str(self.mutation_type),
            task_dir=str(task_dir),
        )
        bound.info("mutation_validate_started")

        try:
            result = self.validate(task_dir, spec)
            bound.info("mutation_validate_finished", valid=result)
            return result
        except Exception:
            bound.exception("mutation_validate_failed")
            raise
