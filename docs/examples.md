# FaultBench Examples

This document demonstrates how to use `pytest-faultbench` through realistic, engineering-focused patterns. These examples show how to leverage simple file mutations to simulate operational failures without heavy architectural additions.

## 1. Minimal Framework Setup (Basics)

- **`mini_app/`**: A minimal app using a simple schema validation function. Demonstrates `schema_drift` catching silent failures.
- **`config_app/`**: A pure python app that requires `DATABASE_URL`. Demonstrates `config_drift`.
- **`flask_app/` & `fastapi_app/`**: Small web apps validating that environment changes natively fail application startup using popular web frameworks.

## 2. Real-World Failure Patterns

The following examples in `examples/real_world_patterns/` prove FaultBench's operational value across common industry outages:

### SQLAlchemy Config Break
- **Location**: `sqlalchemy_config_break/`
- **Simulates**: A standard file-based configuration regression where a mandatory key (e.g., `DATABASE_URL`) drops out of existence.
- **Operational Value**: Ensures that the app strictly validates config and crashes predictably on boot rather than starting in a zombie state or defaulting to a dev database. Uses the `config_drift` mutation.

### Environment Variable Drift
- **Location**: `env_var_drift/`
- **Simulates**: A deployment orchestrator (like Kubernetes or Docker Compose) renaming or dropping a required environment variable (e.g., `DATABASE_URL` -> `DB_URL`) before the application starts.
- **Operational Value**: By reading the mutated `config.json` inside the pytest fixture and injecting it into `os.environ` using `monkeypatch`, we simulate infrastructure-level drift securely within workspace isolation.

### API Contract Break
- **Location**: `api_contract_break/`
- **Simulates**: A downstream microservice API suddenly changing its JSON response shape (e.g. `{"user_id": 123}` becomes `{"id": 123}`) or failing entirely (returning malformed HTML/JSON).
- **Operational Value**: Rather than mutating a python configuration file, the test treats `config.json` as a mock API response payload. Running `config_drift` renames the key, simulating an unannounced API contract breakage and verifying the consumer strictly handles the violation.
