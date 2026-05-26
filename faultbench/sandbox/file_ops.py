"""Filesystem operations for task sandbox preparation.

Handles copying task repositories into working directories, creating
backup snapshots, and cleaning up after execution.  All file operations
that touch the host filesystem before Docker execution happen here.
"""

from __future__ import annotations

import os
import shutil
import stat
from pathlib import Path
from typing import Optional

from faultbench.logging import get_logger

log = get_logger(__name__)


def remove_readonly(func, path, _):
    """Clear the readonly bit and reattempt the removal."""
    os.chmod(path, stat.S_IWRITE)
    func(path)


def copy_task_to_workdir(task_dir: Path, work_dir: Path) -> Path:
    """Copy an entire task repository into a fresh working directory.

    The working directory is where mutations will be applied and the
    agent will operate.  The original task directory is never modified.

    Args:
        task_dir: Path to the original task repo (e.g., ``tasks/task_001_todo_api``).
        work_dir: Parent directory for working copies (e.g., ``logs/runs/``).

    Returns:
        Path to the created working copy.

    Raises:
        FileNotFoundError: If ``task_dir`` does not exist.
        OSError: If the copy fails.
    """
    if not task_dir.exists():
        raise FileNotFoundError(f"Task directory not found: {task_dir}")

    task_name = task_dir.name
    dest = work_dir / task_name

    if dest.exists():
        log.warning("workdir_exists_removing", path=str(dest))
        shutil.rmtree(dest, onerror=remove_readonly)

    log.info("copy_task_start", src=str(task_dir), dest=str(dest))
    shutil.copytree(task_dir, dest)
    log.info("copy_task_complete", dest=str(dest))

    # Initialize a dummy git repo so OpenHands can load it as selected_repository
    import subprocess
    subprocess.run(['git', 'init'], cwd=str(dest), capture_output=True)
    subprocess.run(['git', 'add', '.'], cwd=str(dest), capture_output=True)
    subprocess.run(['git', 'commit', '-m', 'Init'], cwd=str(dest), capture_output=True)

    return dest


def create_backup(target_path: Path, backup_suffix: str = ".bak") -> Path:
    """Create a backup copy of a file or directory.

    Args:
        target_path: File or directory to back up.
        backup_suffix: Suffix to append (default ``.bak``).

    Returns:
        Path to the backup.

    Raises:
        FileNotFoundError: If the target does not exist.
    """
    if not target_path.exists():
        raise FileNotFoundError(f"Cannot backup non-existent path: {target_path}")

    backup_path = target_path.with_suffix(target_path.suffix + backup_suffix)

    if target_path.is_dir():
        if backup_path.exists():
            shutil.rmtree(backup_path, onerror=remove_readonly)
        shutil.copytree(target_path, backup_path)
    else:
        shutil.copy2(target_path, backup_path)

    log.info("backup_created", original=str(target_path), backup=str(backup_path))
    return backup_path


def restore_from_backup(backup_path: Path, target_path: Path) -> None:
    """Restore a file or directory from its backup.

    Args:
        backup_path: Path to the backup.
        target_path: Where to restore to (may or may not exist).

    Raises:
        FileNotFoundError: If the backup does not exist.
    """
    if not backup_path.exists():
        raise FileNotFoundError(f"Backup not found: {backup_path}")

    if target_path.exists():
        if target_path.is_dir():
            shutil.rmtree(target_path, onerror=remove_readonly)
        else:
            target_path.unlink()

    if backup_path.is_dir():
        shutil.copytree(backup_path, target_path)
    else:
        shutil.copy2(backup_path, target_path)

    log.info("restore_from_backup", backup=str(backup_path), target=str(target_path))


def cleanup_workdir(work_dir: Path) -> None:
    """Remove a working directory after a run completes.

    Args:
        work_dir: Directory to remove.
    """
    if work_dir.exists():
        log.info("cleanup_workdir", path=str(work_dir))
        shutil.rmtree(work_dir, onerror=remove_readonly)
    else:
        log.debug("cleanup_workdir_skip", path=str(work_dir), reason="not_found")


def ensure_directory(path: Path) -> Path:
    """Create a directory (and parents) if it doesn't exist.

    Args:
        path: Directory to ensure exists.

    Returns:
        The same path, for chaining.
    """
    path.mkdir(parents=True, exist_ok=True)
    return path


def read_file_text(file_path: Path) -> str:
    """Read a text file, raising a clear error if it doesn't exist.

    Args:
        file_path: Path to the file.

    Returns:
        File contents as a string.

    Raises:
        FileNotFoundError: With a descriptive message.
    """
    if not file_path.exists():
        raise FileNotFoundError(f"Expected file not found: {file_path}")
    return file_path.read_text(encoding="utf-8")


def write_file_text(file_path: Path, content: str) -> None:
    """Write text to a file, creating parent directories if needed.

    Args:
        file_path: Path to the file.
        content: Text content to write.
    """
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(content, encoding="utf-8")
    log.debug("file_written", path=str(file_path), size_bytes=len(content.encode("utf-8")))


def list_files(directory: Path, pattern: str = "*") -> list[Path]:
    """List all files in a directory matching a glob pattern.

    Args:
        directory: Directory to search.
        pattern: Glob pattern (default ``*``).

    Returns:
        Sorted list of matching file paths.
    """
    if not directory.exists():
        return []
    return sorted(directory.glob(pattern))
