from __future__ import annotations

from pathlib import Path

from ms.core.result import Err, Ok, Result
from ms.platform.files import atomic_write_text
from ms.release.errors import ReleaseError


def read_utf8_text(*, path: Path) -> Result[str, ReleaseError]:
    try:
        return Ok(path.read_text(encoding="utf-8"))
    except OSError as error:
        return Err(
            ReleaseError(kind="invalid_input", message=f"failed to read {path}", hint=str(error))
        )


def write_utf8_text_atomic(*, path: Path, content: str) -> Result[None, ReleaseError]:
    try:
        atomic_write_text(path, content, encoding="utf-8")
    except OSError as error:
        return Err(
            ReleaseError(kind="invalid_input", message=f"failed to write {path}", hint=str(error))
        )
    return Ok(None)


__all__ = ["read_utf8_text", "write_utf8_text_atomic"]
