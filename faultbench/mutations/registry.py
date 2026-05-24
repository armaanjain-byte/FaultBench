"""Mutation registry — maps ``MutationType`` to concrete implementations.

Public API
----------
* ``MUTATION_REGISTRY`` — dict mapping each :class:`MutationType` to its
  concrete :class:`BaseMutation` subclass.
* ``get_mutation(mutation_type)`` — factory that returns an *instance* of
  the appropriate mutation class.
* ``get_mutation_spec(task_dir, mutation_type)`` — loads the matching
  :class:`MutationSpec` from the task's ``mutations.yaml``.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from faultbench.constants import MutationType
from faultbench.logging import get_logger
from faultbench.models import MutationAction, MutationSpec

from faultbench.mutations.api_contract_drift import ApiContractDriftMutation
from faultbench.mutations.base import BaseMutation
from faultbench.mutations.config_corruption import ConfigCorruptionMutation
from faultbench.mutations.dependency_drift import DependencyDriftMutation
from faultbench.mutations.missing_file import MissingFileMutation
from faultbench.mutations.schema_drift import SchemaDriftMutation

log = get_logger(__name__)


# ---------------------------------------------------------------------- #
# Registry mapping                                                        #
# ---------------------------------------------------------------------- #

MUTATION_REGISTRY: dict[MutationType, type[BaseMutation]] = {
    MutationType.SCHEMA_DRIFT: SchemaDriftMutation,
    MutationType.DEPENDENCY_DRIFT: DependencyDriftMutation,
    MutationType.CONFIG_CORRUPTION: ConfigCorruptionMutation,
    MutationType.MISSING_FILE: MissingFileMutation,
    MutationType.API_CONTRACT_DRIFT: ApiContractDriftMutation,
}


# ---------------------------------------------------------------------- #
# Factory                                                                  #
# ---------------------------------------------------------------------- #


def get_mutation(mutation_type: MutationType) -> BaseMutation:
    """Return an instance of the mutation class for *mutation_type*.

    Raises:
        KeyError: if *mutation_type* is not registered.
    """
    cls = MUTATION_REGISTRY.get(mutation_type)
    if cls is None:
        raise KeyError(
            f"No mutation registered for {mutation_type!r}.  "
            f"Available: {list(MUTATION_REGISTRY.keys())}"
        )
    log.debug("mutation_instantiated", mutation_type=str(mutation_type))
    return cls()


# ---------------------------------------------------------------------- #
# Spec loader                                                             #
# ---------------------------------------------------------------------- #


def get_mutation_spec(
    task_dir: Path,
    mutation_type: MutationType,
) -> MutationSpec:
    """Load and return the :class:`MutationSpec` for *mutation_type* from
    the ``mutations.yaml`` file inside *task_dir*.

    The YAML file is expected to contain a top-level mapping keyed by
    mutation-type value strings, e.g.::

        schema_drift:
          description: "Rename the users table"
          causal_path: "..."
          actions:
            - action: rename_table
              target: schema.sql
              details:
                file: schema.sql
                old_name: users
                new_name: accounts
          rollback_actions:
            - action: rename_table
              target: schema.sql
              details:
                file: schema.sql
                old_name: accounts
                new_name: users

    Args:
        task_dir: Path to the task directory containing ``mutations.yaml``.
        mutation_type: The mutation type to load.

    Returns:
        A fully-constructed :class:`MutationSpec`.

    Raises:
        FileNotFoundError: if ``mutations.yaml`` does not exist.
        KeyError: if the requested mutation type is not defined in the file.
        ValueError: if the YAML structure is malformed.
    """
    mutations_file = task_dir / "mutations.yaml"
    if not mutations_file.exists():
        raise FileNotFoundError(
            f"mutations.yaml not found in {task_dir}"
        )

    log.info(
        "loading_mutation_spec",
        file=str(mutations_file),
        mutation_type=str(mutation_type),
    )

    raw = yaml.safe_load(mutations_file.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(
            f"Expected a mapping at top level of {mutations_file}, "
            f"got {type(raw).__name__}"
        )

    type_key = str(mutation_type)
    spec_data = raw.get(type_key)
    if spec_data is None:
        raise KeyError(
            f"Mutation type {type_key!r} not found in {mutations_file}.  "
            f"Available: {list(raw.keys())}"
        )

    return _parse_spec(mutation_type, spec_data)


def _parse_spec(
    mutation_type: MutationType,
    data: dict,
) -> MutationSpec:
    """Parse a raw YAML dict into a :class:`MutationSpec`."""
    description = data.get("description", "")
    causal_path = data.get("causal_path", "")

    actions = [_parse_action(a) for a in data.get("actions", [])]
    rollback_actions = [
        _parse_action(a) for a in data.get("rollback_actions", [])
    ]

    return MutationSpec(
        mutation_type=mutation_type,
        description=description,
        causal_path=causal_path,
        actions=actions,
        rollback_actions=rollback_actions,
    )


def _parse_action(data: dict) -> MutationAction:
    """Parse a raw YAML dict into a :class:`MutationAction`."""
    action = data.get("action")
    if not action:
        raise ValueError(f"MutationAction missing 'action' field: {data}")

    target = data.get("target", "")
    details_raw = data.get("details", {})

    # Coerce all detail values to strings for type safety
    details: dict[str, str] = {
        str(k): str(v) for k, v in details_raw.items()
    }

    return MutationAction(action=action, target=target, details=details)
