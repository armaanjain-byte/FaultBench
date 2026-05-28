# Architecture

`pytest-faultbench` is intentionally small. The plugin uses pytest fixtures and hooks to apply mutations to copied workspaces, then reports the result in the terminal.

## Workspace Isolation

Faultbench tests run against a temporary copy of the target directory.

The `mutate` fixture:

1. creates a temporary root directory
2. copies the requested task/app directory into it
3. applies the selected mutation to the copy
4. yields the copied workspace to the test
5. rolls back the mutation
6. removes the temporary root

The source workspace is not edited.

## Mutation Lifecycle

A mutation has two operations:

- `apply(work_dir)`: change files inside the copied workspace
- `rollback(work_dir)`: restore those files after the test

The current plugin resolves mutation names directly in the fixture. There is no registry or framework adapter layer.

## Rollback Guarantees

Rollback runs in the fixture teardown path. If rollback completes, the terminal summary reports:

```text
Rollback successful: YES
```

If rollback raises an exception, the test still surfaces that exception and the summary records:

```text
Rollback successful: NO
```

Temporary workspace cleanup is attempted after rollback handling.

## Reporting Flow

The plugin tracks only four fields per mutation:

- mutation name
- tests affected
- whether any test failed while the mutation was active
- whether rollback succeeded

At session end, `pytest_terminal_summary` renders a compact text summary. There is no persistence layer, report model, dashboard, or telemetry.

## Pytest Integration

The plugin adds:

- `--faultbench`
- `@pytest.mark.faultbench`
- `mutate`
- `faultbench_workdir`

Faultbench-specific tests are skipped by default. They run only when `--faultbench` is passed.

Marker-based tests can provide a workspace through:

```python
@pytest.fixture
def faultbench_task_dir() -> Path:
    return Path("examples/config_app")
```

The `faultbench_workdir` fixture then yields the mutated temporary copy.
