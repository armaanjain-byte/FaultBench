# FaultBench

Resilience testing for environmental and infrastructure assumptions.

`pytest-faultbench` is a pytest plugin that injects controlled faults into an isolated copy of your application workspace, runs your tests against the mutated environment, rolls everything back, and reports what broke and whether it broke correctly.

It is not a fuzzer. It is not a chaos engineering platform. It is a focused tool for one specific problem: **your tests pass, but they only test what you expect to happen — not what happens when the environment stops matching your assumptions.**

---

## The Problem

Applications carry hidden assumptions:

- A config file will have the key `DATABASE_URL`
- `schema.sql` will define a table called `users`
- Config files will be valid JSON

These assumptions are never tested. They live in startup code, initialization logic, and configuration parsers — and they fail silently or catastrophically when a deployment drifts, a schema evolves, or a config is malformed.

`pytest-faultbench` makes those assumptions explicit and testable.

---

## How It Works

For each fault-injection test, the plugin:

1. Copies the target directory into a temporary workspace
2. Applies the named mutation to the copy
3. Runs your test against the mutated workspace
4. Rolls back the mutation and removes the workspace
5. Reports what happened — what was affected, whether failures were detected, whether rollback succeeded

The original files are never modified.

---

## Installation
https://test.pypi.org/project/pytest-faultbench/
```bash
pip install pytest-faultbench
```

Requires Python 3.10+ and pytest 7.0+.

For Flask, FastAPI, and related examples:

```bash
pip install "pytest-faultbench[examples]"
```

---

## Quickstart

Mutation tests are skipped by default. Run them explicitly:

```bash
pytest --faultbench
```

### Marker API

Declare which mutation to apply using a marker. The plugin copies your workspace, applies the mutation, and injects the mutated path as `faultbench_workdir`.

```python
import pytest
from pathlib import Path
from app import get_database_url


@pytest.fixture
def faultbench_task_dir(tmp_path: Path) -> Path:
    """Tell faultbench which directory to copy and mutate."""
    import shutil
    dest = tmp_path / "my_app"
    shutil.copytree(Path(__file__).parent, dest)
    return dest


@pytest.mark.faultbench(mutation="config_drift")
def test_config_drift_detected(faultbench_workdir: Path):
    """config_drift renames DATABASE_URL to DB_URL.
    The app must raise rather than start in a broken state."""
    with pytest.raises(RuntimeError, match="DATABASE_URL missing"):
        get_database_url(faultbench_workdir)
```

### Fixture API

For more control, use the `mutate` context manager directly:

```python
def test_schema_drift_with_context(mutate, tmp_path):
    import shutil
    from app import validate_schema

    source = Path("examples/mini_app")
    dest = tmp_path / "mini_app"
    shutil.copytree(source, dest)

    with mutate(dest, mutation="schema_drift") as work_dir:
        with pytest.raises(RuntimeError, match="Schema may have drifted"):
            validate_schema(work_dir)
```

---

## Mutations

Three mutations are built in. Each operates on files inside the copied workspace and is fully reversed after the test.

### `schema_drift`

Renames every occurrence of `users` to `users_v2` in `schema.sql`.

**Targets:** `schema.sql`

**What it exposes:** whether schema validation, query setup, or startup code catches an unexpected table rename. Apps that silently accept schema drift will pass this test — which is itself a finding.

```python
@pytest.mark.faultbench(mutation="schema_drift")
def test_schema_drift_detected(faultbench_workdir: Path):
    with pytest.raises(RuntimeError, match="Schema may have drifted"):
        validate_schema(faultbench_workdir)
```

---

### `config_drift`

Renames a required configuration key in `config.json`. Specifically renames `DATABASE_URL` → `DB_URL`, or `user_id` → `id` if `DATABASE_URL` is not present.

**Targets:** `config.json`

**What it exposes:** whether required config keys are validated at startup. Apps that start silently with missing config, or fall back to defaults without warning, will pass — again a finding.

```python
@pytest.mark.faultbench(mutation="config_drift")
def test_config_drift_detected(faultbench_workdir: Path):
    with pytest.raises(RuntimeError, match="DATABASE_URL missing"):
        get_database_url(faultbench_workdir)
```

---

### `malformed_config`

Removes the final closing brace from `config.json`, producing invalid JSON.

**Targets:** `config.json`

**What it exposes:** whether config loading raises a clear parse error rather than crashing with an unhandled exception or starting in an undefined state.

```python
@pytest.mark.faultbench(mutation="malformed_config")
def test_malformed_config_fails_cleanly(faultbench_workdir: Path):
    import json
    with pytest.raises(json.JSONDecodeError):
        load_config(faultbench_workdir)
```

---

## `expect_failure`

When you expect a test to fail under a mutation (the fault is working as intended), use `expect_failure=True`. The plugin tracks whether the actual failure matched the expectation and reports a mismatch if it does not.

```python
@pytest.mark.faultbench(mutation="config_drift", expect_failure=True)
def test_api_contract_drift_detected(faultbench_workdir: Path):
    with pytest.raises(KeyError, match="API Contract Violation"):
        process_user(faultbench_workdir)
```

---

## Terminal Output

After a `--faultbench` run, a summary appears at the end of the pytest output:

```
================ FaultBench Summary ================

Mutation: schema_drift
Tests affected: 2
Failures expected: 0
Failures actual: 0
Behavior matched expectation: YES
Rollback successful: YES

Mutation: config_drift
Tests affected: 3
Failures expected: 2
Failures actual: 2
Behavior matched expectation: YES
Rollback successful: YES
```

`Behavior matched expectation: NO` means either a test failed when it was not expected to, or a test passed when it should have failed — both are signal worth investigating.

---

## Adding a Custom Mutation

Import `MUTATION_REGISTRY` and register your class before pytest collects tests. The cleanest place is your `conftest.py`.

```python
# conftest.py
from pathlib import Path
from pytest_faultbench.mutations.base import BaseMutation
from pytest_faultbench.mutations import MUTATION_REGISTRY


class EnvFileMutation(BaseMutation):
    """Remove DATABASE_URL from a .env file."""

    def __init__(self):
        self._original: str | None = None

    def apply(self, work_dir: Path) -> None:
        env_file = work_dir / ".env"
        if not env_file.exists():
            raise RuntimeError(f".env not found in {work_dir}")
        self._original = env_file.read_text()
        lines = [l for l in self._original.splitlines() if not l.startswith("DATABASE_URL")]
        env_file.write_text("\n".join(lines))

    def rollback(self, work_dir: Path) -> None:
        if self._original is None:
            return
        (work_dir / ".env").write_text(self._original)
        self._original = None


MUTATION_REGISTRY["env_file_drift"] = EnvFileMutation
```

Then use it like any built-in:

```python
@pytest.mark.faultbench(mutation="env_file_drift")
def test_missing_env_var_caught(faultbench_workdir: Path):
    ...
```

---

## Fixtures Reference

### `faultbench_workdir`

An isolated, mutated copy of the directory returned by `faultbench_task_dir`. Automatically injected when using `@pytest.mark.faultbench`. Cleaned up after the test.

### `faultbench_task_dir`

Define this fixture in your test file or `conftest.py` to tell the plugin which directory to copy. Return a `Path`.

```python
@pytest.fixture
def faultbench_task_dir(tmp_path: Path) -> Path:
    import shutil
    dest = tmp_path / "my_app"
    shutil.copytree(Path("src/my_app"), dest)
    return dest
```

### `mutate`

A context manager fixture for manual control over the workspace lifecycle.

```python
def test_something(mutate, tmp_path):
    with mutate(tmp_path / "my_app", mutation="schema_drift") as work_dir:
        # work_dir is a mutated copy
        # original is untouched
        ...
    # mutation is rolled back, workspace removed
```

---

## Examples

The `examples/` directory contains runnable examples for common patterns.

| Example | Mutation used | What it tests |
|---|---|---|
| `examples/mini_app/` | `schema_drift` | Schema validation at app startup |
| `examples/config_app/` | `config_drift`, `malformed_config` | Config key validation and parse error handling |
| `examples/flask_app/` | `config_drift`, `malformed_config` | Flask app startup resilience |
| `examples/fastapi_app/` | `config_drift`, `malformed_config` | FastAPI startup resilience |
| `examples/real_world_patterns/env_var_drift/` | `config_drift` | Environment variable drift via config simulation |
| `examples/real_world_patterns/api_contract_break/` | `config_drift`, `malformed_config` | API response contract validation |
| `examples/real_world_patterns/sqlalchemy_config_break/` | `config_drift` | Database connection startup validation |

Run any example:

```bash
# Install example dependencies first
pip install "pytest-faultbench[examples]"

# Baseline (always runs)
pytest examples/mini_app/

# With fault injection
pytest examples/mini_app/ --faultbench
```

---

## Design Decisions

**Mutations run against copies, never originals.** Every test gets a fresh copy of the workspace. The source directory is never touched. If a test crashes mid-mutation, the original is still intact.

**Rollback is always attempted, even if the test fails.** The mutation's `rollback()` runs in a `finally` block. A test failure does not skip cleanup.

**Mutation tests are skipped unless `--faultbench` is passed.** This keeps normal test runs fast. Fault injection tests are opt-in.

**No randomness.** Each mutation is deterministic — the same input always produces the same mutated state. This makes failures reproducible and debuggable.

---

## What FaultBench Is Not

- Not a fuzzer — mutations are explicit and deterministic, not randomly generated
- Not a chaos engineering tool — it does not inject faults at runtime into running processes
- Not a source-code mutation tester — it does not modify logic to find missing test coverage
- Not a load testing tool — it does not simulate traffic or concurrency

Its scope is narrow: validating whether your code detects environmental assumptions becoming invalid.

---

## License

MIT
