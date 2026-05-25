"""Dependency-drift mutation — modifies ``requirements.txt`` package versions.

Supported actions
-----------------
* ``change_version``           — details: ``package``, ``old_version``, ``new_version``
* ``remove_package``           — details: ``package``
* ``add_conflicting_package``  — details: ``conflicting_package``, ``new_version``
* ``replace_string``           — details: ``old_value``, ``new_value``; target: filename
"""

from __future__ import annotations

import re
from pathlib import Path

from faultbench.constants import MutationType
from faultbench.logging import get_logger
from faultbench.models import MutationAction, MutationSpec

from faultbench.mutations.base import BaseMutation

log = get_logger(__name__)


class DependencyDriftMutation(BaseMutation):
    """Inject dependency-level drift into ``requirements.txt``."""

    @property
    def mutation_type(self) -> MutationType:
        return MutationType.DEPENDENCY_DRIFT

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

            if action.action == "change_version":
                package = action.details["package"]
                if not self._package_exists(target_file, package):
                    log.warning(
                        "validation_package_missing",
                        file=str(target_file),
                        package=package,
                    )
                    return False

            if action.action == "remove_package":
                package = action.details["package"]
                if not self._package_exists(target_file, package):
                    log.warning(
                        "validation_package_missing",
                        file=str(target_file),
                        package=package,
                    )
                    return False

        return True

    # ------------------------------------------------------------------ #
    # Dispatch                                                            #
    # ------------------------------------------------------------------ #

    def _dispatch(self, task_dir: Path, action: MutationAction) -> None:
        handlers = {
            "change_version": self._change_version,
            "remove_package": self._remove_package,
            "add_conflicting_package": self._add_conflicting_package,
            "add_package": self._add_package,
            "replace_string": self._replace_string,
        }
        handler = handlers.get(action.action)
        if handler is None:
            raise ValueError(
                f"Unknown dependency_drift action: {action.action!r}"
            )
        handler(task_dir, action)

    # ------------------------------------------------------------------ #
    # change_version                                                      #
    # ------------------------------------------------------------------ #

    def _change_version(self, task_dir: Path, action: MutationAction) -> None:
        details = action.details
        file_path = task_dir / details.get("file", action.target)
        package = details["package"]
        new_version = details["new_version"]

        log.info(
            "change_version",
            file=str(file_path),
            package=package,
            new_version=new_version,
        )

        lines = file_path.read_text(encoding="utf-8").splitlines(keepends=True)
        updated_lines: list[str] = []
        found = False

        for line in lines:
            stripped = line.strip()
            if stripped and not stripped.startswith("#"):
                pkg_name = _parse_package_name(stripped)
                if pkg_name and pkg_name.lower() == package.lower():
                    # Replace the entire line with package==new_version
                    ending = _line_ending(line)
                    updated_lines.append(f"{package}=={new_version}{ending}")
                    found = True
                    continue
            updated_lines.append(line)

        if not found:
            raise ValueError(
                f"Package {package!r} not found in {file_path}"
            )

        file_path.write_text("".join(updated_lines), encoding="utf-8")

    # ------------------------------------------------------------------ #
    # remove_package                                                      #
    # ------------------------------------------------------------------ #

    def _remove_package(self, task_dir: Path, action: MutationAction) -> None:
        details = action.details
        file_path = task_dir / details.get("file", action.target)
        package = details["package"]

        log.info("remove_package", file=str(file_path), package=package)

        lines = file_path.read_text(encoding="utf-8").splitlines(keepends=True)
        updated_lines: list[str] = []
        found = False

        for line in lines:
            stripped = line.strip()
            if stripped and not stripped.startswith("#"):
                pkg_name = _parse_package_name(stripped)
                if pkg_name and pkg_name.lower() == package.lower():
                    found = True
                    continue  # drop the line
            updated_lines.append(line)

        if not found:
            raise ValueError(
                f"Package {package!r} not found in {file_path}"
            )

        file_path.write_text("".join(updated_lines), encoding="utf-8")

    # ------------------------------------------------------------------ #
    # add_conflicting_package                                             #
    # ------------------------------------------------------------------ #

    def _add_conflicting_package(
        self, task_dir: Path, action: MutationAction
    ) -> None:
        details = action.details
        file_path = task_dir / details.get("file", action.target)
        conflicting = details["conflicting_package"]
        version = details.get("new_version", "")

        log.info(
            "add_conflicting_package",
            file=str(file_path),
            conflicting_package=conflicting,
            new_version=version,
        )

        content = file_path.read_text(encoding="utf-8")
        new_line = f"{conflicting}=={version}" if version else conflicting

        # Append at the end, respecting trailing newline
        if content.endswith("\n"):
            content += f"{new_line}\n"
        else:
            content += f"\n{new_line}\n"

        file_path.write_text(content, encoding="utf-8")

    # ------------------------------------------------------------------ #
    # add_package (rollback helper for remove_package)                    #
    # ------------------------------------------------------------------ #

    def _add_package(self, task_dir: Path, action: MutationAction) -> None:
        """Add a package line — used as rollback for ``remove_package``."""
        details = action.details
        file_path = task_dir / details.get("file", action.target)
        package = details["package"]
        version = details.get("new_version", details.get("old_version", ""))

        log.info("add_package", file=str(file_path), package=package)

        content = file_path.read_text(encoding="utf-8")
        new_line = f"{package}=={version}" if version else package

        if content.endswith("\n"):
            content += f"{new_line}\n"
        else:
            content += f"\n{new_line}\n"

        file_path.write_text(content, encoding="utf-8")

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
    # Helpers                                                             #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _package_exists(file_path: Path, package: str) -> bool:
        """Return True if *package* appears as a dependency in the file."""
        lines = file_path.read_text(encoding="utf-8").splitlines()
        for line in lines:
            stripped = line.strip()
            if stripped and not stripped.startswith("#"):
                pkg_name = _parse_package_name(stripped)
                if pkg_name and pkg_name.lower() == package.lower():
                    return True
        return False


# ---------------------------------------------------------------------- #
# Module-level helpers                                                    #
# ---------------------------------------------------------------------- #

# Matches package names from lines like:
#   flask==2.0.1
#   requests>=1.0,<2.0
#   numpy
_PKG_RE = re.compile(r"^([A-Za-z0-9][\w.\-]*)")


def _parse_package_name(line: str) -> str | None:
    """Extract the package name from a requirements.txt line."""
    m = _PKG_RE.match(line.strip())
    return m.group(1) if m else None


def _line_ending(line: str) -> str:
    """Return the line-ending characters of *line*."""
    if line.endswith("\r\n"):
        return "\r\n"
    if line.endswith("\n"):
        return "\n"
    if line.endswith("\r"):
        return "\r"
    return "\n"
