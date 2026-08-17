from __future__ import annotations

import json
from pathlib import Path

from ms.core.result import Err, Ok, Result
from ms.core.structured import as_str_dict
from ms.platform.files import atomic_write_text
from ms.release.errors import ReleaseError

_SESSION_SCHEMA = 3


def write_session(*, path: Path, payload: dict[str, object]) -> Result[None, ReleaseError]:
    payload = {**payload, "schema": _SESSION_SCHEMA}
    try:
        atomic_write_text(path, json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    except OSError as exc:
        return Err(
            ReleaseError(
                kind="repo_failed",
                message=f"failed to write release session: {exc}",
                hint=str(path),
            )
        )
    return Ok(None)


def read_session(*, path: Path) -> Result[dict[str, object] | None, ReleaseError]:
    if not path.exists():
        return Ok(None)

    try:
        raw: object = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return Err(
            ReleaseError(
                kind="invalid_input",
                message=f"failed to load release session: {exc}",
                hint=str(path),
            )
        )

    data = as_str_dict(raw)
    if data is None:
        return Err(
            ReleaseError(
                kind="invalid_input",
                message="invalid release session format",
                hint=str(path),
            )
        )
    if data.get("schema") != _SESSION_SCHEMA:
        return Err(
            ReleaseError(
                kind="invalid_input",
                message=f"unsupported release session schema: {data.get('schema')}",
                hint=str(path),
            )
        )
    return Ok(data)


def clear_session(*, path: Path) -> Result[None, ReleaseError]:
    try:
        path.unlink(missing_ok=True)
    except OSError as exc:
        return Err(
            ReleaseError(
                kind="repo_failed",
                message=f"failed to delete release session: {exc}",
                hint=str(path),
            )
        )
    return Ok(None)
