from __future__ import annotations

from dataclasses import asdict
from pathlib import Path

from ms.core.result import Err, Ok, Result
from ms.core.structured import get_str, get_table
from ms.release.errors import ReleaseError

from .session_models import AppReleaseSession, SessionCursor
from .session_parse import get_int, parse_app_step, parse_bump, parse_channel, parse_pending_inputs
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

    cursor_data = get_table(data, "cursor")
    pending_inputs = parse_pending_inputs(data.get("pending_inputs"))

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
        or cursor_data is None
        or pending_inputs is None
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
            schema=4,
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
            cursor=SessionCursor(
                channel=get_int(cursor_data, name="channel", default=0),
                bump=get_int(cursor_data, name="bump", default=0),
                sha=get_int(cursor_data, name="sha", default=0),
                summary=get_int(cursor_data, name="summary", default=0),
                return_to_summary=bool(cursor_data.get("return_to_summary", False)),
            ),
            pending_kind=get_str(data, "pending_kind"),
            pending_request_id=get_str(data, "pending_request_id"),
            pending_repo=get_str(data, "pending_repo"),
            pending_workflow=get_str(data, "pending_workflow"),
            pending_tag=get_str(data, "pending_tag"),
            pending_source_sha=get_str(data, "pending_source_sha"),
            pending_tooling_sha=get_str(data, "pending_tooling_sha"),
            pending_at=get_str(data, "pending_at"),
            pending_inputs=pending_inputs,
        )
    )


def clear_app_session(*, workspace_root: Path) -> Result[None, ReleaseError]:
    return clear_session(path=app_session_path(workspace_root=workspace_root))
