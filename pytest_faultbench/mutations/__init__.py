from pytest_faultbench.mutations.config_drift import ConfigDriftMutation
from pytest_faultbench.mutations.malformed_config import MalformedConfigMutation
from pytest_faultbench.mutations.schema_drift import SchemaDriftMutation

MUTATION_REGISTRY = {
    "schema_drift": SchemaDriftMutation,
    "config_drift": ConfigDriftMutation,
    "malformed_config": MalformedConfigMutation,
}

__all__ = ["MUTATION_REGISTRY"]
