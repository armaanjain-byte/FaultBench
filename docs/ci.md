# Continuous Integration with FaultBench

Resilience testing must be reproducible. While running `pytest --faultbench` locally is great for development, adding it to your CI pipeline ensures that your application continuously detects infrastructure breakages.

## Why CI Matters for Resilience Testing

Local environments are often carefully curated. CI provides a clean room that enforces reproducible environmental assumptions. Running FaultBench in CI guarantees that:
- Your application correctly identifies configuration drift, missing databases, and malformed files in a non-local setting.
- Future code changes don't accidentally silence startup errors or mask missing infrastructure.
- Tests that encode resilience remain valid.

## Running FaultBench in CI

Because `pytest-faultbench` is a standard pytest plugin, no external databases, containers, or enterprise orchestration systems are required. 

A minimal GitHub Actions workflow looks like this:

```yaml
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
      
      - name: Install
        run: pip install -e . pytest
        
      - name: Normal tests
        run: pytest
        
      - name: Resilience tests
        run: pytest --faultbench
```

## Interpreting CI Outputs

When you run `pytest --faultbench` in CI, the terminal will print a summary of the mutations tested.

### A Test Failure is Often GOOD

In FaultBench, a "failed" application state is usually exactly what you're testing for. 

If the `schema_drift` mutation is applied and your app crashes with `RuntimeError("Schema missing")`, the test asserting that crash **passes**. The test successfully proved the app doesn't silently ignore a broken database.

### What if a mutation causes NO test failures?

If `Failures detected: NO` appears, it means the mutation was active, but the test suite passed anyway. 

Depending on your test, this might mean:
1. **Graceful Degradation:** Your app correctly detected the missing config and gracefully fell back to a default. (This is good!)
2. **Missing Coverage (Resilience Gap):** Your app silently ignored the corrupted config and tried to continue anyway, but your tests didn't catch the bad state. (This is bad.)

Use CI output to spot missing resilience gaps and force the application to fail loudly when assumptions break.
