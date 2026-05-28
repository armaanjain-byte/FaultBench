# pytest-faultbench

Resilience testing for environmental and infrastructure assumptions.

`pytest-faultbench` is a small pytest plugin for checking how an application behaves when common runtime assumptions are broken. It mutates an isolated copy of a task or app workspace, runs normal pytest tests against that mutated workspace, rolls the mutation back, and prints a compact terminal summary.

It is not an observability platform, a mutation testing clone, or a framework abstraction layer. It is a focused tool for making hidden assumptions visible during tests.

## Problem Statement

Applications often assume their environment is stable:

- database schema names are unchanged
- required config keys exist
- config files parse correctly
- startup validation catches bad infrastructure state

Those assumptions fail in production-like systems. `pytest-faultbench` gives contributors a simple way to encode those failure modes as pytest tests and verify that the app detects or survives them.

## Core Concept

A faultbench test runs inside an isolated workspace:

1. copy the target task/app directory to a temporary workspace
2. apply one named mutation
3. run the test against the mutated copy
4. roll the mutation back
5. remove the temporary workspace
6. report whether the mutation caused a test failure and whether rollback succeeded

The original files are not mutated.

## Installation

From a local checkout:

```bash
python -m pip install -e .
```

To run the Flask and FastAPI examples, install the optional example dependencies:

```bash
python -m pip install -e ".[examples]"
```

## Quickstart

Write a test that declares a target workspace and marks the mutation to apply:

```python
from pathlib import Path

import pytest


@pytest.fixture
def faultbench_task_dir() -> Path:
    return Path("examples/config_app")


@pytest.mark.faultbench(mutation="config_drift")
def test_app_rejects_missing_database_url(faultbench_workdir: Path):
    from app import get_database_url

    with pytest.raises(RuntimeError, match="DATABASE_URL missing"):
        get_database_url(faultbench_workdir)
```

Run faultbench tests explicitly:

```bash
pytest --faultbench
```

Tests using `mutate`, `faultbench_workdir`, or `@pytest.mark.faultbench` are skipped unless `--faultbench` is provided.

## Example Mutation Workflow

For a `config.json` file like:

```json
{
  "DATABASE_URL": "sqlite:///app.db"
}
```

The `config_drift` mutation rewrites `DATABASE_URL` to `DB_URL` inside the temporary workspace. Your test can then assert that app startup fails clearly instead of silently continuing with invalid configuration.

## Example Terminal Output

```text
================ FaultBench Summary ================

Mutation: config_drift
Tests affected: 1
Failures detected: NO
Rollback successful: YES

Mutation: malformed_config
Tests affected: 1
Failures detected: NO
Rollback successful: YES
```

`Failures detected: NO` means no test failed while that mutation was active. That can be expected if the test asserts graceful handling, or it can signal a resilience gap if the mutation should have been detected by the application.

## Continuous Integration

Running FaultBench in CI proves your app's resilience assumptions in a clean, non-local environment. Because it is a simple pytest plugin, integration is trivial:

```yaml
# .github/workflows/tests.yml
name: Tests
on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      
      - run: pip install -e . pytest
      - run: pytest -v
      - run: pytest --faultbench -v
```

**Why are mutation failures useful?**

A mutation-caused failure in your application is often **GOOD**. It proves your tests successfully detected environmental breakage (like configuration drift or a missing schema). If a destructive mutation applies and causes *no* failures, it may indicate missing test coverage or hidden, dangerous assumptions that your app silently swallows. See [docs/ci.md](docs/ci.md) for more details.

## Real-world failure patterns

FaultBench helps you detect silent outages by demonstrating realistic environmental breakages across your tests. Rather than assuming the environment is static, it proves that your application correctly identifies:

- **Configuration Drift**: A local config drops required keys (e.g., `DATABASE_URL` renamed).
- **Environment Variable Drift**: A deployment orchestrator silently mangles environment state (simulated by dynamically mapping mutated config files to `os.environ` inside your tests).
- **API Contract Breaks**: A downstream microservice API suddenly changes its JSON response payload shape (e.g., `user_id` -> `id`), caught cleanly without complex mocking frameworks.

See [docs/examples.md](docs/examples.md) for these engineering-focused examples.

## Supported Mutations

- `schema_drift`: renames `users` to `users_v2` in `schema.sql`
- `config_drift`: renames `DATABASE_URL` to `DB_URL` in `config.json`
- `malformed_config`: removes the final closing brace from `config.json`

See [docs/mutations.md](docs/mutations.md) for details.

## Framework Compatibility

`pytest-faultbench` does not use framework-specific adapters. It works through pytest fixtures and temporary workspaces.

Current examples validate:

- plain Python config loading
- a minimal schema-backed app
- Flask startup validation
- FastAPI startup validation

See [docs/examples.md](docs/examples.md).

## Project Philosophy

- Prefer small, realistic failure modes over broad simulation.
- Keep pytest as the integration surface.
- Keep mutations explicit and easy to inspect.
- Keep reporting terminal-first and readable.
- Avoid persistence, dashboards, telemetry, and framework-specific runtime hooks.

## Roadmap

Near-term:

- document more realistic failure patterns
- improve example coverage around common infrastructure assumptions
- keep rollback behavior simple and well tested

Later:

- add carefully scoped mutations when backed by real use cases
- improve contributor guidance for adding examples
- evaluate packaging and release workflow once the core behavior settles

Non-goals for now:

- dashboards
- databases
- cloud execution
- CI orchestration
- plugin registries
- telemetry

## Contributing

Start by reading:

- [docs/architecture.md](docs/architecture.md)
- [docs/mutations.md](docs/mutations.md)
- [docs/examples.md](docs/examples.md)

Development loop:

```bash
python -m pip install -e ".[examples]"
pytest
pytest --faultbench
```

Keep contributions focused. New behavior should preserve workspace isolation, rollback safety, and minimal terminal reporting.
