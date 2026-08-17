from __future__ import annotations

from dataclasses import asdict
from pathlib import Path

from ms.core.result import Err, Ok, Result
from ms.core.structured import get_str
from ms.release.errors import ReleaseError

from .session_models import AppReleaseSession
from .session_parse import get_int, parse_app_step, parse_bump, parse_channel
from .session_paths import app_session_path
from .session_store import clear_session, read_session, write_session


def save_app_session(
    *, workspace_root: Path, session: AppReleaseSession
) -> Result[None, ReleaseError]:
    return write_session(
        path=app_session_path(workspace_root=workspace_root),
        payload=asdict(session),
    )


def load_app_session(*, workspace_root: Path) -> Result[AppReleaseSession | None, ReleaseError]:
    path = app_session_path(workspace_root=workspace_root)
    loaded = read_session(path=path)
    if isinstance(loaded, Err):
        return loaded
    if loaded.value is None:
        return Ok(None)
    data = loaded.value

    release_id = get_str(data, "release_id")
    created_at = get_str(data, "created_at")
    created_by = get_str(data, "created_by")
    step = parse_app_step(get_str(data, "step"))
    product = get_str(data, "product")
    repo_ref = get_str(data, "repo_ref")

    if (
        release_id is None
        or created_at is None
        or created_by is None
        or step is None
        or product != "app"
        or repo_ref is None
    ):
        return Err(
            ReleaseError(
                kind="invalid_input",
                message="release session missing required fields",
                hint=str(path),
            )
        )

    return Ok(
        AppReleaseSession(
            schema=3,
            release_id=release_id,
            created_at=created_at,
            created_by=created_by,
            step=step,
            product="app",
            channel=parse_channel(get_str(data, "channel")),
            bump=parse_bump(get_str(data, "bump")),
            tag=get_str(data, "tag"),
            version=get_str(data, "version"),
            tooling_sha=get_str(data, "tooling_sha"),
            repo_ref=repo_ref,
            repo_sha=get_str(data, "repo_sha"),
            notes_path=get_str(data, "notes_path"),
            notes_markdown=get_str(data, "notes_markdown"),
            notes_sha256=get_str(data, "notes_sha256"),
            idx_channel=get_int(data, name="idx_channel", default=0),
            idx_bump=get_int(data, name="idx_bump", default=0),
            idx_sha=get_int(data, name="idx_sha", default=0),
            idx_summary=get_int(data, name="idx_summary", default=0),
            return_to_summary=bool(data.get("return_to_summary", False)),
        )
    )


def clear_app_session(*, workspace_root: Path) -> Result[None, ReleaseError]:
    return clear_session(path=app_session_path(workspace_root=workspace_root))
