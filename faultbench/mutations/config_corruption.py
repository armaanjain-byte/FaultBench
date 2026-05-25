"""Config-corruption mutation — corrupts YAML and JSON configuration files.

Supported actions
-----------------
* ``corrupt_yaml``    — details: ``file``, ``corruption_type`` (one of
  ``syntax_error``, ``invalid_encoding``, ``duplicate_key``)
* ``change_value``    — details: ``file``, ``key_path`` (dot-separated),
  ``old_value``, ``new_value``
* ``remove_key``      — details: ``file``, ``key_path``
* ``add_invalid_key`` — details: ``file``, ``key_path``, ``new_value``
* ``add_key``         — alias/rollback helper identical to ``add_invalid_key``
* ``set_value``       — rollback helper identical to ``change_value``
* ``replace_string``  — details: ``old_value``, ``new_value``; target: filename
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml

from faultbench.constants import MutationType
from faultbench.logging import get_logger
from faultbench.models import MutationAction, MutationSpec

from faultbench.mutations.base import BaseMutation

log = get_logger(__name__)


class ConfigCorruptionMutation(BaseMutation):
    """Inject configuration-level corruption into YAML / JSON files."""

    @property
    def mutation_type(self) -> MutationType:
        return MutationType.CONFIG_CORRUPTION

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
        return True

    # ------------------------------------------------------------------ #
    # Dispatch                                                            #
    # ------------------------------------------------------------------ #

    def _dispatch(self, task_dir: Path, action: MutationAction) -> None:
        handlers: dict[str, Any] = {
            "corrupt_yaml": self._corrupt_yaml,
            "change_value": self._change_value,
            "remove_key": self._remove_key,
            "add_invalid_key": self._add_key,
            "add_key": self._add_key,
            "set_value": self._change_value,
            "restore_file": self._restore_file,
            "replace_string": self._replace_string,
        }
        handler = handlers.get(action.action)
        if handler is None:
            raise ValueError(
                f"Unknown config_corruption action: {action.action!r}"
            )
        handler(task_dir, action)

    # ------------------------------------------------------------------ #
    # corrupt_yaml                                                        #
    # ------------------------------------------------------------------ #

    def _corrupt_yaml(self, task_dir: Path, action: MutationAction) -> None:
        """Introduce syntactic corruption into a YAML (or JSON) file.

        The ``corruption_type`` detail selects the flavour:
        * ``syntax_error``      — insert an un-parseable line near the top
        * ``invalid_encoding``  — inject raw bytes that break UTF-8 parsing
        * ``duplicate_key``     — duplicate the first key so loaders may
          silently overwrite or error
        """
        details = action.details
        file_path = task_dir / details.get("file", action.target)
        corruption_type = details.get("corruption_type", "syntax_error")

        log.info(
            "corrupt_yaml",
            file=str(file_path),
            corruption_type=corruption_type,
        )

        # Save a backup so rollback can restore the original
        backup = file_path.with_suffix(file_path.suffix + ".bak")
        backup.write_bytes(file_path.read_bytes())

        content = file_path.read_text(encoding="utf-8")

        if corruption_type == "syntax_error":
            # Insert an invalid YAML line after the first line
            lines = content.splitlines(keepends=True)
            corruption_line = "{{{{INVALID: [unterminated\n"
            if lines:
                lines.insert(1, corruption_line)
            else:
                lines.append(corruption_line)
            file_path.write_text("".join(lines), encoding="utf-8")

        elif corruption_type == "invalid_encoding":
            raw = file_path.read_bytes()
            # Insert 4 non-UTF-8 bytes after the first newline
            bad_bytes = b"\xfe\xff\x80\x81"
            idx = raw.find(b"\n")
            if idx >= 0:
                raw = raw[: idx + 1] + bad_bytes + raw[idx + 1 :]
            else:
                raw = raw + bad_bytes
            file_path.write_bytes(raw)

        elif corruption_type == "duplicate_key":
            lines = content.splitlines(keepends=True)
            # Find the first non-comment, non-blank line and duplicate it
            for i, line in enumerate(lines):
                stripped = line.strip()
                if stripped and not stripped.startswith("#") and ":" in stripped:
                    lines.insert(i + 1, line)
                    break
            file_path.write_text("".join(lines), encoding="utf-8")

        else:
            raise ValueError(f"Unknown corruption_type: {corruption_type!r}")

    # ------------------------------------------------------------------ #
    # change_value / set_value                                            #
    # ------------------------------------------------------------------ #

    def _change_value(self, task_dir: Path, action: MutationAction) -> None:
        """Change a value at *key_path* in a YAML or JSON file."""
        details = action.details
        file_path = task_dir / details.get("file", action.target)
        key_path = details["key_path"]
        new_value = details["new_value"]

        log.info(
            "change_value",
            file=str(file_path),
            key_path=key_path,
            new_value=new_value,
        )

        data = self._load(file_path)
        keys = key_path.split(".")
        _set_nested(data, keys, _coerce_value(new_value))
        self._dump(file_path, data)

    # ------------------------------------------------------------------ #
    # remove_key                                                          #
    # ------------------------------------------------------------------ #

    def _remove_key(self, task_dir: Path, action: MutationAction) -> None:
        """Remove a key (and its value) at *key_path*."""
        details = action.details
        file_path = task_dir / details.get("file", action.target)
        key_path = details["key_path"]

        log.info("remove_key", file=str(file_path), key_path=key_path)

        data = self._load(file_path)
        keys = key_path.split(".")
        _delete_nested(data, keys)
        self._dump(file_path, data)

    # ------------------------------------------------------------------ #
    # add_key / add_invalid_key                                           #
    # ------------------------------------------------------------------ #

    def _add_key(self, task_dir: Path, action: MutationAction) -> None:
        """Add (or overwrite) a key at *key_path* with *new_value*."""
        details = action.details
        file_path = task_dir / details.get("file", action.target)
        key_path = details["key_path"]
        new_value = details["new_value"]

        log.info(
            "add_key",
            file=str(file_path),
            key_path=key_path,
            new_value=new_value,
        )

        data = self._load(file_path)
        keys = key_path.split(".")
        _set_nested(data, keys, _coerce_value(new_value))
        self._dump(file_path, data)

    # ------------------------------------------------------------------ #
    # restore_file (rollback helper for corrupt_yaml)                     #
    # ------------------------------------------------------------------ #

    def _restore_file(self, task_dir: Path, action: MutationAction) -> None:
        """Restore a file from its ``.bak`` backup."""
        details = action.details
        file_path = task_dir / details.get("file", action.target)
        backup = file_path.with_suffix(file_path.suffix + ".bak")

        log.info("restore_file", file=str(file_path), backup=str(backup))

        if not backup.exists():
            raise FileNotFoundError(
                f"Backup file not found: {backup}"
            )

        file_path.write_bytes(backup.read_bytes())
        backup.unlink()

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
    # Load / dump helpers                                                 #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _load(file_path: Path) -> dict[str, Any]:
        """Load a YAML or JSON file into a dict."""
        content = file_path.read_text(encoding="utf-8")
        if file_path.suffix in (".json",):
            data = json.loads(content)
        else:
            data = yaml.safe_load(content)

        if not isinstance(data, dict):
            raise ValueError(
                f"Expected a mapping at top level of {file_path}, got {type(data).__name__}"
            )
        return data

    @staticmethod
    def _dump(file_path: Path, data: dict[str, Any]) -> None:
        """Write a dict back to a YAML or JSON file."""
        if file_path.suffix in (".json",):
            content = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
        else:
            content = yaml.dump(
                data,
                default_flow_style=False,
                allow_unicode=True,
                sort_keys=False,
            )
        file_path.write_text(content, encoding="utf-8")


# ---------------------------------------------------------------------- #
# Module-level helpers                                                    #
# ---------------------------------------------------------------------- #


def _set_nested(data: dict[str, Any], keys: list[str], value: Any) -> None:
    """Set a value at a nested key path, creating intermediate dicts."""
    current = data
    for key in keys[:-1]:
        if key not in current or not isinstance(current[key], dict):
            current[key] = {}
        current = current[key]
    current[keys[-1]] = value


def _delete_nested(data: dict[str, Any], keys: list[str]) -> None:
    """Delete a key at a nested key path."""
    current = data
    for key in keys[:-1]:
        if key not in current or not isinstance(current[key], dict):
            raise KeyError(f"Key path segment {key!r} not found")
        current = current[key]
    if keys[-1] not in current:
        raise KeyError(f"Key {keys[-1]!r} not found at path {'->'.join(keys)}")
    del current[keys[-1]]


def _coerce_value(raw: str) -> Any:
    """Best-effort coercion of a string value to a Python type.

    Tries int → float → bool → ``None`` → falls back to str.
    """
    if raw.lower() == "true":
        return True
    if raw.lower() == "false":
        return False
    if raw.lower() == "null" or raw.lower() == "none":
        return None
    try:
        return int(raw)
    except ValueError:
        pass
    try:
        return float(raw)
    except ValueError:
        pass
    return raw
