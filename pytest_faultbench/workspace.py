from __future__ import annotations

import shutil
import stat
from pathlib import Path


def copy_to_tmp(source: Path, tmp_root: Path) -> Path:
    """Copy *source* directory into *tmp_root* and return the copied path."""
    dest = tmp_root / source.name
    shutil.copytree(source, dest)
    return dest


def remove(path: Path) -> None:
    """Remove directory tree, handling Windows read-only files."""

    def _on_error(_func, fpath, _exc_info):
        Path(fpath).chmod(stat.S_IWRITE)
        Path(fpath).unlink()

    shutil.rmtree(path, onexc=_on_error)
