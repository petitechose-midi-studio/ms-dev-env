from __future__ import annotations

import os
import tempfile
from pathlib import Path

from ms.core.result import Err, Ok, Result
from ms.release.errors import ReleaseError


def read_utf8_text(*, path: Path) -> Result[str, ReleaseError]:
    try:
        return Ok(path.read_text(encoding="utf-8"))
    except OSError as error:
        return Err(
            ReleaseError(kind="invalid_input", message=f"failed to read {path}", hint=str(error))
        )


def write_utf8_text_atomic(*, path: Path, content: str) -> Result[None, ReleaseError]:
    tmp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            newline="\n",
            delete=False,
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
        ) as handle:
            handle.write(content)
            tmp_path = Path(handle.name)
        os.replace(tmp_path, path)
    except OSError as error:
        if tmp_path is not None:
            try:
                tmp_path.unlink(missing_ok=True)
            except OSError:
                pass
        return Err(
            ReleaseError(kind="invalid_input", message=f"failed to write {path}", hint=str(error))
        )
    return Ok(None)


__all__ = ["read_utf8_text", "write_utf8_text_atomic"]
