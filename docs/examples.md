# Examples

The examples are small on purpose. They show how faultbench tests map to realistic app assumptions without adding framework-specific support code.

## mini_app

Location:

```text
examples/mini_app
```

Purpose:

- demonstrates schema-focused validation
- uses `schema.sql`
- shows how `schema_drift` exposes assumptions about database structure

Use this example when working on schema mutation behavior or rollback safety.

## config_app

Location:

```text
examples/config_app
```

Purpose:

- demonstrates plain Python config loading
- uses `config.json`
- shows how `config_drift` and `malformed_config` affect startup-style validation

Use this example when working on config mutation behavior without framework dependencies.

## flask_app

Location:

```text
examples/flask_app
```

Purpose:

- validates compatibility with a minimal Flask app
- loads `DATABASE_URL` from `config.json`
- exposes `/health`
- raises at app creation if config is invalid

The tests prove that faultbench can mutate a real Flask app workspace without Flask-specific plugin code.

## fastapi_app

Location:

```text
examples/fastapi_app
```

Purpose:

- validates compatibility with a minimal FastAPI app
- loads `DATABASE_URL` from `config.json`
- exposes `/health`
- raises at app creation if config is invalid

The tests prove that faultbench can validate startup assumptions in FastAPI through normal pytest usage.

## Running Examples

Install example dependencies:

```bash
python -m pip install -e ".[examples]"
```

Run all project tests:

```bash
pytest
pytest --faultbench
```

Run framework examples directly:

```bash
pytest examples/flask_app --faultbench
pytest examples/fastapi_app --faultbench
```
