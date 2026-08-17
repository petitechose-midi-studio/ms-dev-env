"""Filesystem helpers."""

from __future__ import annotations

import os
import shutil
import stat
import tempfile
from collections.abc import Callable
from contextlib import suppress
from pathlib import Path

__all__ = ["atomic_write_text", "remove_tree"]


def _remove_readonly(func: Callable[[str], object], path: str, exc: BaseException) -> None:
    if not isinstance(exc, PermissionError):
        raise exc
    os.chmod(path, stat.S_IWRITE)
    func(path)


def remove_tree(path: Path) -> None:
    """Remove a directory tree, including read-only files on Windows."""
    shutil.rmtree(path, onexc=_remove_readonly)


def atomic_write_text(path: Path, content: str, *, encoding: str = "utf-8") -> None:
    """Write text to path atomically using temp file + replace."""
    path.parent.mkdir(parents=True, exist_ok=True)

    fd, tmp_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=str(path.parent),
    )
    tmp_path = Path(tmp_name)

    try:
        with os.fdopen(fd, "w", encoding=encoding, newline="") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_path, path)
    finally:
        with suppress(OSError):
            tmp_path.unlink(missing_ok=True)
