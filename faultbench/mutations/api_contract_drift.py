"""API-contract-drift mutation — modifies API structures in source files.

Uses regex-based text replacement to change response fields, endpoint
paths, and HTTP status codes in Python source files.

Supported actions
-----------------
* ``change_response_field`` — details: ``file``, ``field_name``,
  ``pattern``, ``replacement``
* ``change_endpoint``       — details: ``file``, ``old_path``, ``new_path``
* ``change_status_code``    — details: ``file``, ``pattern``, ``replacement``
* ``replace_string``        — details: ``old_value``, ``new_value``; target: filename
* ``add_import``            — details: ``import_line``; target: filename
* ``remove_import``         — details: ``import_line``; target: filename
"""

from __future__ import annotations

import re
from pathlib import Path

from faultbench.constants import MutationType
from faultbench.logging import get_logger
from faultbench.models import MutationAction, MutationSpec

from faultbench.mutations.base import BaseMutation

log = get_logger(__name__)


class ApiContractDriftMutation(BaseMutation):
    """Inject API-contract–level drift into Python source files."""

    @property
    def mutation_type(self) -> MutationType:
        return MutationType.API_CONTRACT_DRIFT

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
            target_file = task_dir / action.details.get("file", action.target)
            if not target_file.exists():
                log.warning(
                    "validation_file_missing",
                    file=str(target_file),
                    action=action.action,
                )
                return False

            # For pattern-based actions, verify the pattern exists in the file
            content = target_file.read_text(encoding="utf-8")

            if action.action == "change_response_field":
                pattern = action.details.get("pattern", "")
                if pattern and not re.search(pattern, content):
                    log.warning(
                        "validation_pattern_not_found",
                        file=str(target_file),
                        pattern=pattern,
                    )
                    return False

            elif action.action == "change_endpoint":
                old_path = action.details["old_path"]
                if old_path not in content:
                    log.warning(
                        "validation_endpoint_not_found",
                        file=str(target_file),
                        old_path=old_path,
                    )
                    return False

            elif action.action == "change_status_code":
                pattern = action.details.get("pattern", "")
                if pattern and not re.search(pattern, content):
                    log.warning(
                        "validation_pattern_not_found",
                        file=str(target_file),
                        pattern=pattern,
                    )
                    return False

        return True

    # ------------------------------------------------------------------ #
    # Dispatch                                                            #
    # ------------------------------------------------------------------ #

    def _dispatch(self, task_dir: Path, action: MutationAction) -> None:
        handlers = {
            "change_response_field": self._change_response_field,
            "change_endpoint": self._change_endpoint,
            "change_status_code": self._change_status_code,
            "replace_string": self._replace_string,
            "add_import": self._add_import,
            "remove_import": self._remove_import,
        }
        handler = handlers.get(action.action)
        if handler is None:
            raise ValueError(
                f"Unknown api_contract_drift action: {action.action!r}"
            )
        handler(task_dir, action)

    # ------------------------------------------------------------------ #
    # change_response_field                                               #
    # ------------------------------------------------------------------ #

    def _change_response_field(
        self, task_dir: Path, action: MutationAction
    ) -> None:
        """Replace a response field name or structure using a regex pattern.

        If ``pattern`` / ``replacement`` are provided, they are used directly.
        Otherwise a whole-word replacement of ``field_name`` → ``replacement``
        is performed.
        """
        details = action.details
        file_path = task_dir / details.get("file", action.target)

        pattern = details.get("pattern", "")
        replacement = details.get("replacement", "")
        field_name = details.get("field_name", "")

        log.info(
            "change_response_field",
            file=str(file_path),
            field_name=field_name,
            pattern=pattern,
        )

        content = file_path.read_text(encoding="utf-8")

        if pattern:
            updated = re.sub(pattern, replacement, content)
        elif field_name and replacement:
            # Whole-word replacement of the field name
            updated = re.sub(
                rf"\b{re.escape(field_name)}\b", replacement, content
            )
        else:
            raise ValueError(
                "change_response_field requires either 'pattern'+'replacement' "
                "or 'field_name'+'replacement'"
            )

        if updated == content:
            log.warning(
                "no_replacements_made",
                file=str(file_path),
                pattern=pattern or field_name,
            )

        file_path.write_text(updated, encoding="utf-8")

    # ------------------------------------------------------------------ #
    # change_endpoint                                                     #
    # ------------------------------------------------------------------ #

    def _change_endpoint(self, task_dir: Path, action: MutationAction) -> None:
        """Replace an API endpoint path with a new path."""
        details = action.details
        file_path = task_dir / details.get("file", action.target)
        old_path = details["old_path"]
        new_path = details["new_path"]

        log.info(
            "change_endpoint",
            file=str(file_path),
            old_path=old_path,
            new_path=new_path,
        )

        content = file_path.read_text(encoding="utf-8")
        updated = content.replace(old_path, new_path)

        if updated == content:
            log.warning(
                "no_replacements_made",
                file=str(file_path),
                old_path=old_path,
            )

        file_path.write_text(updated, encoding="utf-8")

    # ------------------------------------------------------------------ #
    # change_status_code                                                  #
    # ------------------------------------------------------------------ #

    def _change_status_code(
        self, task_dir: Path, action: MutationAction
    ) -> None:
        """Replace HTTP status codes using a regex pattern."""
        details = action.details
        file_path = task_dir / details.get("file", action.target)
        pattern = details["pattern"]
        replacement = details["replacement"]

        log.info(
            "change_status_code",
            file=str(file_path),
            pattern=pattern,
            replacement=replacement,
        )

        content = file_path.read_text(encoding="utf-8")
        updated = re.sub(pattern, replacement, content)

        if updated == content:
            log.warning(
                "no_replacements_made",
                file=str(file_path),
                pattern=pattern,
            )

        file_path.write_text(updated, encoding="utf-8")

    # ------------------------------------------------------------------ #
    # replace_string                                                      #
    # ------------------------------------------------------------------ #

    def _replace_string(self, task_dir: Path, action: MutationAction) -> None:
        """Perform a literal string replacement in a file."""
        details = action.details
        file_path = task_dir / details.get("file", action.target)
        old_value = details["old_value"]
        new_value = details["new_value"]

        log.info(
            "replace_string",
            file=str(file_path),
            old_value=old_value,
            new_value=new_value,
        )

        self.replace_string_in_file(file_path, old_value, new_value)

    # ------------------------------------------------------------------ #
    # add_import / remove_import                                          #
    # ------------------------------------------------------------------ #

    def _add_import(self, task_dir: Path, action: MutationAction) -> None:
        """Prepend an import line to a Python source file."""
        details = action.details
        file_path = task_dir / details.get("file", action.target)
        import_line = details["import_line"]

        log.info("add_import", file=str(file_path), import_line=import_line)

        content = file_path.read_text(encoding="utf-8")
        if import_line not in content:
            file_path.write_text(import_line + "\n" + content, encoding="utf-8")

    def _remove_import(self, task_dir: Path, action: MutationAction) -> None:
        """Remove a specific import line from a Python source file."""
        details = action.details
        file_path = task_dir / details.get("file", action.target)
        import_line = details["import_line"]

        log.info("remove_import", file=str(file_path), import_line=import_line)

        lines = file_path.read_text(encoding="utf-8").splitlines(keepends=True)
        updated = [line for line in lines if line.rstrip("\r\n") != import_line]
        file_path.write_text("".join(updated), encoding="utf-8")
