-- FaultBench Database Schema
-- ==========================
-- SQLite schema for benchmark result storage.
-- All access goes through faultbench.db.store.BenchmarkStore.

-- runs table — one row per benchmark run
CREATE TABLE IF NOT EXISTS runs (
    run_id             TEXT PRIMARY KEY,
    task_name          TEXT NOT NULL,
    agent_name         TEXT NOT NULL,
    mutation_type      TEXT,              -- NULL means clean baseline
    mutation_timing    TEXT,              -- "before" only in v1
    success            INTEGER NOT NULL,  -- 0 or 1
    retry_count        INTEGER NOT NULL,
    runtime_seconds    REAL NOT NULL,
    tokens_used        INTEGER,           -- null if agent doesn't expose
    exception_count    INTEGER NOT NULL,
    first_failure_step INTEGER,           -- which agent step first failed
    raw_log_path       TEXT,
    created_at         REAL NOT NULL      -- unix timestamp
);

-- Indexes for the queries comparator.py runs constantly
CREATE INDEX IF NOT EXISTS idx_task_mutation  ON runs(task_name, mutation_type);
CREATE INDEX IF NOT EXISTS idx_task_agent     ON runs(task_name, agent_name);
CREATE INDEX IF NOT EXISTS idx_mutation_only  ON runs(mutation_type);
