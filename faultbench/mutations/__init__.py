"""FaultBench mutation engine — controlled environmental fault injection.

This package contains one module per mutation type plus a registry that
maps :class:`~faultbench.constants.MutationType` enum values to their
concrete implementations.

Quick-start::

    from faultbench.mutations import get_mutation, get_mutation_spec
    from faultbench.constants import MutationType

    spec = get_mutation_spec(task_dir, MutationType.SCHEMA_DRIFT)
    mutation = get_mutation(MutationType.SCHEMA_DRIFT)
    mutation.safe_apply(task_dir, spec)
    # … run agent …
    mutation.safe_rollback(task_dir, spec)
"""

from __future__ import annotations

from faultbench.mutations.api_contract_drift import ApiContractDriftMutation
from faultbench.mutations.base import BaseMutation
from faultbench.mutations.config_corruption import ConfigCorruptionMutation
from faultbench.mutations.dependency_drift import DependencyDriftMutation
from faultbench.mutations.missing_file import MissingFileMutation
from faultbench.mutations.registry import (
    MUTATION_REGISTRY,
    get_mutation,
    get_mutation_spec,
)
from faultbench.mutations.schema_drift import SchemaDriftMutation

__all__ = [
    # Base
    "BaseMutation",
    # Concrete mutations
    "SchemaDriftMutation",
    "DependencyDriftMutation",
    "ConfigCorruptionMutation",
    "MissingFileMutation",
    "ApiContractDriftMutation",
    # Registry
    "MUTATION_REGISTRY",
    "get_mutation",
    "get_mutation_spec",
]
