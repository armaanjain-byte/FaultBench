"""Centralized SQLite persistence layer for FaultBench.

All database access in the application goes through :class:`BenchmarkStore`.
No raw SQL is scattered across other modules — this is the single point
of contact with SQLite.

Features:
- Automatic schema initialization on first connect
- Parameterized queries only (no SQL injection surface)
- Clean transaction handling with context managers
- Helper methods for every query the system needs
"""

from __future__ import annotations

import importlib.resources
import sqlite3
from pathlib import Path
from typing import Optional

from faultbench.logging import get_logger
from faultbench.models import RunRecord

log = get_logger(__name__)


class BenchmarkStore:
    """SQLite-backed storage for benchmark run records.

    Usage::

        store = BenchmarkStore("db/faultbench.db")
        store.insert_run(run_record)
        runs = store.get_runs_by_task("task_001_todo_api")
        store.close()

    Or as a context manager::

        with BenchmarkStore("db/faultbench.db") as store:
            store.insert_run(run_record)
    """

    def __init__(self, db_path: str) -> None:
        self._db_path = db_path
        self._conn: Optional[sqlite3.Connection] = None
        self._ensure_directory()
        self._connect()
        self._initialize_schema()

    def _ensure_directory(self) -> None:
        """Create parent directories for the database file if needed."""
        db_dir = Path(self._db_path).parent
        db_dir.mkdir(parents=True, exist_ok=True)

    def _connect(self) -> None:
        """Open a connection to the SQLite database."""
        log.info("db_connecting", path=self._db_path)
        self._conn = sqlite3.connect(self._db_path)
        self._conn.row_factory = sqlite3.Row
        # Enable WAL mode for better concurrent read performance
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        log.info("db_connected", path=self._db_path)

    def _initialize_schema(self) -> None:
        """Execute the schema SQL to create tables if they don't exist."""
        schema_path = Path(__file__).parent / "schema.sql"
        if not schema_path.exists():
            raise FileNotFoundError(
                f"Schema file not found at {schema_path}. "
                "The faultbench package may be installed incorrectly."
            )

        schema_sql = schema_path.read_text(encoding="utf-8")
        assert self._conn is not None
        self._conn.executescript(schema_sql)
        self._conn.commit()
        log.info("db_schema_initialized")

    @property
    def connection(self) -> sqlite3.Connection:
        """Return the active connection, raising if closed."""
        if self._conn is None:
            raise RuntimeError("BenchmarkStore is closed")
        return self._conn

    # ------------------------------------------------------------------
    # Write operations
    # ------------------------------------------------------------------

    def insert_run(self, record: RunRecord) -> None:
        """Insert a single run record into the database.

        Args:
            record: A fully populated RunRecord.

        Raises:
            sqlite3.IntegrityError: If ``run_id`` already exists.
        """
        log.info(
            "db_insert_run",
            run_id=record.run_id,
            task=record.task_name,
            mutation=record.mutation_type,
            success=record.success,
        )
        self.connection.execute(
            """
            INSERT INTO runs (
                run_id, task_name, agent_name, mutation_type, mutation_timing,
                success, retry_count, runtime_seconds, tokens_used,
                exception_count, first_failure_step, raw_log_path, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record.run_id,
                record.task_name,
                record.agent_name,
                record.mutation_type,
                record.mutation_timing,
                1 if record.success else 0,
                record.retry_count,
                record.runtime_seconds,
                record.tokens_used,
                record.exception_count,
                record.first_failure_step,
                record.raw_log_path,
                record.created_at,
            ),
        )
        self.connection.commit()

    def insert_runs(self, records: list[RunRecord]) -> None:
        """Batch insert multiple run records in a single transaction."""
        log.info("db_insert_runs_batch", count=len(records))
        try:
            for record in records:
                self.connection.execute(
                    """
                    INSERT INTO runs (
                        run_id, task_name, agent_name, mutation_type,
                        mutation_timing, success, retry_count, runtime_seconds,
                        tokens_used, exception_count, first_failure_step,
                        raw_log_path, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        record.run_id,
                        record.task_name,
                        record.agent_name,
                        record.mutation_type,
                        record.mutation_timing,
                        1 if record.success else 0,
                        record.retry_count,
                        record.runtime_seconds,
                        record.tokens_used,
                        record.exception_count,
                        record.first_failure_step,
                        record.raw_log_path,
                        record.created_at,
                    ),
                )
            self.connection.commit()
            log.info("db_insert_runs_batch_complete", count=len(records))
        except Exception:
            self.connection.rollback()
            log.exception("db_insert_runs_batch_failed")
            raise

    def delete_run(self, run_id: str) -> bool:
        """Delete a run by its ID.  Returns True if a row was deleted."""
        cursor = self.connection.execute(
            "DELETE FROM runs WHERE run_id = ?", (run_id,)
        )
        self.connection.commit()
        deleted = cursor.rowcount > 0
        log.info("db_delete_run", run_id=run_id, deleted=deleted)
        return deleted

    # ------------------------------------------------------------------
    # Read operations
    # ------------------------------------------------------------------

    def _rows_to_records(self, rows: list[sqlite3.Row]) -> list[RunRecord]:
        """Convert sqlite3.Row objects to RunRecord dataclasses."""
        records: list[RunRecord] = []
        for row in rows:
            records.append(
                RunRecord(
                    run_id=row["run_id"],
                    task_name=row["task_name"],
                    agent_name=row["agent_name"],
                    mutation_type=row["mutation_type"],
                    mutation_timing=row["mutation_timing"],
                    success=bool(row["success"]),
                    retry_count=row["retry_count"],
                    runtime_seconds=row["runtime_seconds"],
                    tokens_used=row["tokens_used"],
                    exception_count=row["exception_count"],
                    first_failure_step=row["first_failure_step"],
                    raw_log_path=row["raw_log_path"],
                    created_at=row["created_at"],
                )
            )
        return records

    def get_run(self, run_id: str) -> Optional[RunRecord]:
        """Fetch a single run by ID."""
        cursor = self.connection.execute(
            "SELECT * FROM runs WHERE run_id = ?", (run_id,)
        )
        row = cursor.fetchone()
        if row is None:
            return None
        return self._rows_to_records([row])[0]

    def get_runs_by_task(
        self, task_name: str, *, agent_name: Optional[str] = None
    ) -> list[RunRecord]:
        """Get all runs for a specific task, optionally filtered by agent."""
        if agent_name:
            cursor = self.connection.execute(
                "SELECT * FROM runs WHERE task_name = ? AND agent_name = ? ORDER BY created_at",
                (task_name, agent_name),
            )
        else:
            cursor = self.connection.execute(
                "SELECT * FROM runs WHERE task_name = ? ORDER BY created_at",
                (task_name,),
            )
        return self._rows_to_records(cursor.fetchall())

    def get_baseline_runs(
        self, task_name: str, agent_name: Optional[str] = None
    ) -> list[RunRecord]:
        """Get clean baseline runs (mutation_type IS NULL) for a task."""
        if agent_name:
            cursor = self.connection.execute(
                """SELECT * FROM runs
                   WHERE task_name = ? AND agent_name = ? AND mutation_type IS NULL
                   ORDER BY created_at""",
                (task_name, agent_name),
            )
        else:
            cursor = self.connection.execute(
                """SELECT * FROM runs
                   WHERE task_name = ? AND mutation_type IS NULL
                   ORDER BY created_at""",
                (task_name,),
            )
        return self._rows_to_records(cursor.fetchall())

    def get_mutated_runs(
        self,
        task_name: str,
        mutation_type: str,
        agent_name: Optional[str] = None,
    ) -> list[RunRecord]:
        """Get runs for a specific task + mutation combination."""
        if agent_name:
            cursor = self.connection.execute(
                """SELECT * FROM runs
                   WHERE task_name = ? AND mutation_type = ? AND agent_name = ?
                   ORDER BY created_at""",
                (task_name, mutation_type, agent_name),
            )
        else:
            cursor = self.connection.execute(
                """SELECT * FROM runs
                   WHERE task_name = ? AND mutation_type = ?
                   ORDER BY created_at""",
                (task_name, mutation_type),
            )
        return self._rows_to_records(cursor.fetchall())

    def get_all_runs(self) -> list[RunRecord]:
        """Return every run in the database, ordered by creation time."""
        cursor = self.connection.execute(
            "SELECT * FROM runs ORDER BY created_at"
        )
        return self._rows_to_records(cursor.fetchall())

    def get_distinct_tasks(self) -> list[str]:
        """Return all unique task names that have at least one run."""
        cursor = self.connection.execute(
            "SELECT DISTINCT task_name FROM runs ORDER BY task_name"
        )
        return [row["task_name"] for row in cursor.fetchall()]

    def get_distinct_mutations(self) -> list[str]:
        """Return all unique non-null mutation types in the database."""
        cursor = self.connection.execute(
            """SELECT DISTINCT mutation_type FROM runs
               WHERE mutation_type IS NOT NULL
               ORDER BY mutation_type"""
        )
        return [row["mutation_type"] for row in cursor.fetchall()]

    def get_run_count(
        self,
        task_name: Optional[str] = None,
        mutation_type: Optional[str] = None,
    ) -> int:
        """Count runs with optional filters."""
        conditions: list[str] = []
        params: list[str] = []

        if task_name is not None:
            conditions.append("task_name = ?")
            params.append(task_name)
        if mutation_type is not None:
            conditions.append("mutation_type = ?")
            params.append(mutation_type)
        elif mutation_type is None and task_name is not None:
            # Don't filter mutation_type unless explicitly requested
            pass

        where_clause = " AND ".join(conditions) if conditions else "1=1"
        cursor = self.connection.execute(
            f"SELECT COUNT(*) as cnt FROM runs WHERE {where_clause}",
            params,
        )
        row = cursor.fetchone()
        return row["cnt"] if row else 0

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def close(self) -> None:
        """Close the database connection."""
        if self._conn is not None:
            self._conn.close()
            self._conn = None
            log.info("db_closed", path=self._db_path)

    def __enter__(self) -> BenchmarkStore:
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:  # type: ignore[no-untyped-def]
        self.close()
