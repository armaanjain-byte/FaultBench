"""Schema-drift mutation — renames columns, tables, and changes column types.

Operates on ``.sql`` text files (regex-based replacement) and ``.db`` SQLite
database files (ALTER TABLE / column-map recreation).  Each action in the
spec's ``actions`` list is dispatched to a handler by the ``action`` field.

Supported actions
-----------------
* ``rename_column``  — details: ``file``, ``table``, ``old_name``, ``new_name``
* ``rename_table``   — details: ``file``, ``old_name``, ``new_name``
* ``change_column_type`` — details: ``file``, ``table``, ``column``, ``new_type``
"""

from __future__ import annotations

import re
import shutil
import sqlite3
from pathlib import Path

from faultbench.constants import MutationType
from faultbench.logging import get_logger
from faultbench.models import MutationAction, MutationSpec

from faultbench.mutations.base import BaseMutation

log = get_logger(__name__)


class SchemaDriftMutation(BaseMutation):
    """Inject schema-level changes into SQL or SQLite files."""

    @property
    def mutation_type(self) -> MutationType:
        return MutationType.SCHEMA_DRIFT

    # ------------------------------------------------------------------ #
    # Public interface                                                    #
    # ------------------------------------------------------------------ #

    def apply(self, task_dir: Path, spec: MutationSpec) -> None:
        """Apply every action listed in *spec.actions*."""
        for action in spec.actions:
            self._dispatch(task_dir, action)

    def rollback(self, task_dir: Path, spec: MutationSpec) -> None:
        """Apply rollback_actions (which are the inverse operations)."""
        for action in spec.rollback_actions:
            self._dispatch(task_dir, action)

    def validate(self, task_dir: Path, spec: MutationSpec) -> bool:
        """Ensure every referenced file exists and is readable."""
        for action in spec.actions:
            target_file = task_dir / action.details.get("file", action.target)
            if not target_file.exists():
                log.warning(
                    "validation_file_missing",
                    file=str(target_file),
                    action=action.action,
                )
                return False
        return True

    # ------------------------------------------------------------------ #
    # Dispatch                                                            #
    # ------------------------------------------------------------------ #

    def _dispatch(self, task_dir: Path, action: MutationAction) -> None:
        handlers = {
            "rename_column": self._rename_column,
            "rename_table": self._rename_table,
            "change_column_type": self._change_column_type,
        }
        handler = handlers.get(action.action)
        if handler is None:
            raise ValueError(f"Unknown schema_drift action: {action.action!r}")
        handler(task_dir, action)

    # ------------------------------------------------------------------ #
    # rename_column                                                       #
    # ------------------------------------------------------------------ #

    def _rename_column(self, task_dir: Path, action: MutationAction) -> None:
        details = action.details
        file_path = task_dir / details["file"]
        old_name = details["old_name"]
        new_name = details["new_name"]

        log.info(
            "rename_column",
            file=str(file_path),
            old_name=old_name,
            new_name=new_name,
        )

        if file_path.suffix == ".db":
            self._rename_column_sqlite(file_path, details["table"], old_name, new_name)
        else:
            self._regex_replace_in_file(file_path, old_name, new_name)

    def _rename_column_sqlite(
        self,
        db_path: Path,
        table: str,
        old_name: str,
        new_name: str,
    ) -> None:
        """Rename a column in a SQLite database using ALTER TABLE."""
        conn = sqlite3.connect(str(db_path))
        try:
            conn.execute(
                f"ALTER TABLE {_quote_ident(table)} "
                f"RENAME COLUMN {_quote_ident(old_name)} "
                f"TO {_quote_ident(new_name)}"
            )
            conn.commit()
        finally:
            conn.close()

    # ------------------------------------------------------------------ #
    # rename_table                                                        #
    # ------------------------------------------------------------------ #

    def _rename_table(self, task_dir: Path, action: MutationAction) -> None:
        details = action.details
        file_path = task_dir / details["file"]
        old_name = details["old_name"]
        new_name = details["new_name"]

        log.info(
            "rename_table",
            file=str(file_path),
            old_name=old_name,
            new_name=new_name,
        )

        if file_path.suffix == ".db":
            self._rename_table_sqlite(file_path, old_name, new_name)
        else:
            self._regex_replace_in_file(file_path, old_name, new_name)

    def _rename_table_sqlite(
        self, db_path: Path, old_name: str, new_name: str
    ) -> None:
        conn = sqlite3.connect(str(db_path))
        try:
            conn.execute(
                f"ALTER TABLE {_quote_ident(old_name)} "
                f"RENAME TO {_quote_ident(new_name)}"
            )
            conn.commit()
        finally:
            conn.close()

    # ------------------------------------------------------------------ #
    # change_column_type                                                  #
    # ------------------------------------------------------------------ #

    def _change_column_type(self, task_dir: Path, action: MutationAction) -> None:
        """Change a column's type.

        For ``.sql`` files we do a regex replacement on the column definition.
        For ``.db`` files we recreate the table with the new column type
        because SQLite does not support ALTER COLUMN directly.
        """
        details = action.details
        file_path = task_dir / details["file"]
        table = details["table"]
        column = details["column"]
        new_type = details["new_type"]

        log.info(
            "change_column_type",
            file=str(file_path),
            table=table,
            column=column,
            new_type=new_type,
        )

        if file_path.suffix == ".db":
            self._change_column_type_sqlite(file_path, table, column, new_type)
        else:
            # In .sql text, match `column_name CURRENT_TYPE` and replace the type
            pattern = rf"(?i)(\b{re.escape(column)}\b\s+)\w+"
            replacement = rf"\g<1>{new_type}"
            self._regex_replace_in_file_pattern(file_path, pattern, replacement)

    def _change_column_type_sqlite(
        self,
        db_path: Path,
        table: str,
        column: str,
        new_type: str,
    ) -> None:
        """Recreate the table with the altered column type.

        SQLite ≥ 3.35 supports ALTER TABLE … DROP COLUMN but not
        ALTER COLUMN, so we use the 12-step table-rebuild approach.
        """
        conn = sqlite3.connect(str(db_path))
        try:
            cursor = conn.execute(f"PRAGMA table_info({_quote_ident(table)})")
            columns = cursor.fetchall()
            if not columns:
                raise ValueError(f"Table {table!r} not found in {db_path}")

            col_names: list[str] = []
            col_defs: list[str] = []
            found = False
            for col in columns:
                # col = (cid, name, type, notnull, default, pk)
                name = col[1]
                col_type = col[2]
                not_null = " NOT NULL" if col[3] else ""
                pk = " PRIMARY KEY" if col[5] else ""

                if name.lower() == column.lower():
                    col_type = new_type
                    found = True

                col_names.append(_quote_ident(name))
                col_defs.append(f"{_quote_ident(name)} {col_type}{not_null}{pk}")

            if not found:
                raise ValueError(
                    f"Column {column!r} not found in table {table!r}"
                )

            tmp_table = f"_faultbench_tmp_{table}"
            col_defs_str = ", ".join(col_defs)
            col_names_str = ", ".join(col_names)

            conn.execute("BEGIN TRANSACTION")
            conn.execute(f"CREATE TABLE {_quote_ident(tmp_table)} ({col_defs_str})")
            conn.execute(
                f"INSERT INTO {_quote_ident(tmp_table)} ({col_names_str}) "
                f"SELECT {col_names_str} FROM {_quote_ident(table)}"
            )
            conn.execute(f"DROP TABLE {_quote_ident(table)}")
            conn.execute(
                f"ALTER TABLE {_quote_ident(tmp_table)} "
                f"RENAME TO {_quote_ident(table)}"
            )
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    # ------------------------------------------------------------------ #
    # File-level helpers                                                  #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _regex_replace_in_file(file_path: Path, old: str, new: str) -> None:
        """Replace all *whole-word* occurrences of *old* with *new* in a text file."""
        content = file_path.read_text(encoding="utf-8")
        pattern = rf"\b{re.escape(old)}\b"
        updated = re.sub(pattern, new, content)
        if updated == content:
            log.warning("no_replacements_made", file=str(file_path), old=old)
        file_path.write_text(updated, encoding="utf-8")

    @staticmethod
    def _regex_replace_in_file_pattern(
        file_path: Path, pattern: str, replacement: str
    ) -> None:
        """Apply an arbitrary regex replacement to a text file."""
        content = file_path.read_text(encoding="utf-8")
        updated = re.sub(pattern, replacement, content)
        if updated == content:
            log.warning(
                "no_replacements_made", file=str(file_path), pattern=pattern
            )
        file_path.write_text(updated, encoding="utf-8")


# ---------------------------------------------------------------------- #
# Module-level helpers                                                    #
# ---------------------------------------------------------------------- #

def _quote_ident(identifier: str) -> str:
    """Double-quote a SQL identifier, escaping embedded quotes."""
    escaped = identifier.replace('"', '""')
    return f'"{escaped}"'
