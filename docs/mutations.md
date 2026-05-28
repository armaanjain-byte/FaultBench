# Mutations

Mutations simulate environmental and infrastructure assumption failures. They operate on copied workspaces and are rolled back after each test.

## schema_drift

Simulates a database schema naming change.

Behavior:

- reads `schema.sql`
- replaces `users` with `users_v2`

Why it matters:

Applications often assume table names or schema fragments stay stable. A schema drift test checks whether startup, validation, or query-building code catches unexpected schema changes.

Expected failure modes:

- schema validation fails
- query setup fails
- app startup rejects the schema
- tests reveal that the app silently accepts the drift

## config_drift

Simulates a required configuration key being renamed.

Behavior:

- reads `config.json`
- replaces `DATABASE_URL` with `DB_URL`

Why it matters:

Services often rely on required config keys for infrastructure dependencies. This mutation checks whether missing required configuration is detected clearly.

Expected failure modes:

- startup validation raises `RuntimeError`
- config loading rejects missing `DATABASE_URL`
- tests reveal fallback behavior that hides invalid config

## malformed_config

Simulates invalid JSON configuration.

Behavior:

- reads `config.json`
- removes the final closing brace

Why it matters:

Configuration files can be truncated, partially written, or malformed. Apps should fail clearly instead of starting in an undefined state.

Expected failure modes:

- JSON parsing raises `json.JSONDecodeError`
- startup fails before serving requests
- tests reveal missing validation around config loading
