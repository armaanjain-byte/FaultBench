# Hello World Benchmark Task

A minimal FaultBench benchmark task to verify the full pipeline works end-to-end.

## Purpose

This task is intentionally the simplest possible benchmark:

- **Repo**: a single `hello.py` file
- **Fault**: a typo in the print statement (`"helo wrld"` instead of `"hello world"`)
- **Agent task**: fix the typo
- **Verification**: `python hello.py` must exit 0 and print `hello world`

## Files

| File | Purpose |
|---|---|
| `hello.py` | The faulty script (initial state) |
| `task.yaml` | Task configuration (instruction, verify command, timeout) |
| `mutations.yaml` | No-op placeholders (baseline-only task) |

## Running this benchmark

```bash
# One baseline run
faultbench run --task task_hello_world --mutation none --runs 1

# Verbose logging
FAULTBENCH_LOG_LEVEL=DEBUG faultbench run --task task_hello_world --mutation none --runs 1
```

## Expected behavior

1. FaultBench copies `hello.py` to a temp working directory
2. Sends the instruction to OpenHands
3. OpenHands edits `hello.py` to fix the typo
4. FaultBench runs `python hello.py` in the working directory
5. Exit code 0 → `success=True`
6. RunRecord is saved to `db/faultbench.db`
