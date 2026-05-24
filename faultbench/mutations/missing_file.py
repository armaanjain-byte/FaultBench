"""Missing-file mutation — deletes, renames, or truncates critical files.

Every destructive action creates a backup so that ``rollback`` can fully
restore the original state.

Supported actions
-----------------
* ``delete_file``   — details: ``file``, optional ``backup_suffix`` (default ``.faultbench_bak``)
* ``rename_file``   — details: ``file``, ``new_name``
* ``truncate_file`` — details: ``file``, optional ``backup_suffix``
* ``restore_file``  — rollback helper: restores from backup
* ``unrename_file``  — rollback helper: reverses a rename
"""

from __future__ import annotations

import shutil
from pathlib import Path

from faultbench.constants import MutationType
from faultbench.logging import get_logger
from faultbench.models import MutationAction, MutationSpec

from faultbench.mutations.base import BaseMutation

log = get_logger(__name__)

_DEFAULT_BACKUP_SUFFIX = ".faultbench_bak"


class MissingFileMutation(BaseMutation):
    """Delete, rename, or truncate files to simulate missing-file faults."""

    @property
    def mutation_type(self) -> MutationType:
        return MutationType.MISSING_FILE

    # ------------------------------------------------------------------ #
    # Public interface                                                    #
    # ------------------------------------------------------------------ #

    def apply(self, task_dir: Path, spec: MutationSpec) -> None:
        for action in spec.actions:
            self._dispatch(task_dir, action)

    def rollback(self, task_dir: Path, spec: MutationSpec) -> None:
        for action in spec.rollback_actions:
            self._dispatch(task_dir, action)

    def validate(self, task_dir: Path, spec: MutationSpec) -> bool:
        for action in spec.actions:
            details = action.details
            target_file = task_dir / details.get("file", action.target)

            if action.action in ("delete_file", "truncate_file"):
                if not target_file.exists():
                    log.warning(
                        "validation_file_missing",
                        file=str(target_file),
                        action=action.action,
                    )
                    return False

            elif action.action == "rename_file":
                if not target_file.exists():
                    log.warning(
                        "validation_file_missing",
                        file=str(target_file),
                        action=action.action,
                    )
                    return False
                new_path = target_file.parent / details["new_name"]
                if new_path.exists():
                    log.warning(
                        "validation_rename_target_exists",
                        file=str(new_path),
                        action=action.action,
                    )
                    return False

        return True

    # ------------------------------------------------------------------ #
    # Dispatch                                                            #
    # ------------------------------------------------------------------ #

    def _dispatch(self, task_dir: Path, action: MutationAction) -> None:
        handlers = {
            "delete_file": self._delete_file,
            "rename_file": self._rename_file,
            "truncate_file": self._truncate_file,
            "restore_file": self._restore_file,
            "unrename_file": self._unrename_file,
        }
        handler = handlers.get(action.action)
        if handler is None:
            raise ValueError(
                f"Unknown missing_file action: {action.action!r}"
            )
        handler(task_dir, action)

    # ------------------------------------------------------------------ #
    # delete_file                                                         #
    # ------------------------------------------------------------------ #

    def _delete_file(self, task_dir: Path, action: MutationAction) -> None:
        details = action.details
        file_path = task_dir / details.get("file", action.target)
        backup_suffix = details.get("backup_suffix", _DEFAULT_BACKUP_SUFFIX)
        backup_path = file_path.with_suffix(file_path.suffix + backup_suffix)

        log.info(
            "delete_file",
            file=str(file_path),
            backup=str(backup_path),
        )

        if not file_path.exists():
            raise FileNotFoundError(f"Cannot delete: {file_path} does not exist")

        # Create backup before deletion
        shutil.copy2(str(file_path), str(backup_path))
        file_path.unlink()

    # ------------------------------------------------------------------ #
    # rename_file                                                         #
    # ------------------------------------------------------------------ #

    def _rename_file(self, task_dir: Path, action: MutationAction) -> None:
        details = action.details
        file_path = task_dir / details.get("file", action.target)
        new_name = details["new_name"]
        new_path = file_path.parent / new_name

        log.info(
            "rename_file",
            old=str(file_path),
            new=str(new_path),
        )

        if not file_path.exists():
            raise FileNotFoundError(
                f"Cannot rename: {file_path} does not exist"
            )
        if new_path.exists():
            raise FileExistsError(
                f"Cannot rename: target {new_path} already exists"
            )

        file_path.rename(new_path)

    # ------------------------------------------------------------------ #
    # truncate_file                                                       #
    # ------------------------------------------------------------------ #

    def _truncate_file(self, task_dir: Path, action: MutationAction) -> None:
        """Truncate a file to zero bytes, preserving a backup."""
        details = action.details
        file_path = task_dir / details.get("file", action.target)
        backup_suffix = details.get("backup_suffix", _DEFAULT_BACKUP_SUFFIX)
        backup_path = file_path.with_suffix(file_path.suffix + backup_suffix)

        log.info(
            "truncate_file",
            file=str(file_path),
            backup=str(backup_path),
        )

        if not file_path.exists():
            raise FileNotFoundError(
                f"Cannot truncate: {file_path} does not exist"
            )

        # Backup original content
        shutil.copy2(str(file_path), str(backup_path))
        # Truncate to zero bytes
        file_path.write_bytes(b"")

    # ------------------------------------------------------------------ #
    # restore_file (rollback for delete_file / truncate_file)             #
    # ------------------------------------------------------------------ #

    def _restore_file(self, task_dir: Path, action: MutationAction) -> None:
        """Restore a file from its backup."""
        details = action.details
        file_path = task_dir / details.get("file", action.target)
        backup_suffix = details.get("backup_suffix", _DEFAULT_BACKUP_SUFFIX)
        backup_path = file_path.with_suffix(file_path.suffix + backup_suffix)

        log.info(
            "restore_file",
            file=str(file_path),
            backup=str(backup_path),
        )

        if not backup_path.exists():
            raise FileNotFoundError(
                f"Backup not found: {backup_path}"
            )

        shutil.copy2(str(backup_path), str(file_path))
        backup_path.unlink()

    # ------------------------------------------------------------------ #
    # unrename_file (rollback for rename_file)                            #
    # ------------------------------------------------------------------ #

    def _unrename_file(self, task_dir: Path, action: MutationAction) -> None:
        """Reverse a rename — moves the file from ``new_name`` back to ``file``."""
        details = action.details
        original_path = task_dir / details.get("file", action.target)
        current_name = details["new_name"]
        current_path = original_path.parent / current_name

        log.info(
            "unrename_file",
            current=str(current_path),
            original=str(original_path),
        )

        if not current_path.exists():
            raise FileNotFoundError(
                f"Cannot unrename: {current_path} does not exist"
            )

        current_path.rename(original_path)
