from __future__ import annotations

import json
from pathlib import Path

from ms.core.result import Err, Ok, Result
from ms.core.structured import as_obj_list, as_str_dict, get_str
from ms.platform.files import atomic_write_text
from ms.release.errors import ReleaseError

from .session_models import ContentReleaseSession
from .session_parse import get_int, parse_bump, parse_channel, parse_content_step
from .session_paths import content_session_path


def save_content_session(
    *, workspace_root: Path, session: ContentReleaseSession
) -> Result[None, ReleaseError]:
    path = content_session_path(workspace_root=workspace_root)
    payload: dict[str, object] = {
        "schema": 3,
        "release_id": session.release_id,
        "created_at": session.created_at,
        "created_by": session.created_by,
        "step": session.step,
        "product": session.product,
        "channel": session.channel,
        "bump": session.bump,
        "tag": session.tag,
        "repo_cursor": session.repo_cursor,
        "repo_shas": [{"id": rid, "sha": sha} for rid, sha in session.repo_shas],
        "notes_path": session.notes_path,
        "notes_markdown": session.notes_markdown,
        "notes_sha256": session.notes_sha256,
        "idx_channel": session.idx_channel,
        "idx_bump": session.idx_bump,
        "idx_repo": session.idx_repo,
        "idx_summary": session.idx_summary,
        "idx_candidates": session.idx_candidates,
        "return_to_summary": session.return_to_summary,
    }

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


def load_content_session(
    *, workspace_root: Path
) -> Result[ContentReleaseSession | None, ReleaseError]:
    path = content_session_path(workspace_root=workspace_root)
    if not path.exists():
        return Ok(None)

    try:
        text = path.read_text(encoding="utf-8")
        raw: object = json.loads(text)
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

    if data.get("schema") not in {2, 3}:
        return Err(
            ReleaseError(
                kind="invalid_input",
                message=f"unsupported release session schema: {data.get('schema')}",
                hint=str(path),
            )
        )

    release_id = get_str(data, "release_id")
    created_at = get_str(data, "created_at")
    created_by = get_str(data, "created_by")
    step = parse_content_step(get_str(data, "step"))
    product = get_str(data, "product")
    repo_cursor_obj = data.get("repo_cursor")

    if (
        release_id is None
        or created_at is None
        or created_by is None
        or step is None
        or product != "content"
        or not isinstance(repo_cursor_obj, int)
    ):
        return Err(
            ReleaseError(
                kind="invalid_input",
                message="release session missing required fields",
                hint=str(path),
            )
        )

    parsed_repo_shas: list[tuple[str, str]] = []
    repo_shas_raw: list[object] | None = as_obj_list(data.get("repo_shas"))
    if repo_shas_raw is not None:
        for item in repo_shas_raw:
            row = as_str_dict(item)
            if row is None:
                continue
            repo_id = get_str(row, "id")
            sha = get_str(row, "sha")
            if repo_id is None or sha is None:
                continue
            parsed_repo_shas.append((repo_id, sha))

    return Ok(
        ContentReleaseSession(
            schema=3,
            release_id=release_id,
            created_at=created_at,
            created_by=created_by,
            step=step,
            product="content",
            channel=parse_channel(get_str(data, "channel")),
            bump=parse_bump(get_str(data, "bump")),
            tag=get_str(data, "tag"),
            repo_cursor=max(0, repo_cursor_obj),
            repo_shas=tuple(parsed_repo_shas),
            notes_path=get_str(data, "notes_path"),
            notes_markdown=get_str(data, "notes_markdown"),
            notes_sha256=get_str(data, "notes_sha256"),
            idx_channel=get_int(data, name="idx_channel", default=0),
            idx_bump=get_int(data, name="idx_bump", default=0),
            idx_repo=get_int(data, name="idx_repo", default=0),
            idx_summary=get_int(data, name="idx_summary", default=0),
            idx_candidates=get_int(data, name="idx_candidates", default=0),
            return_to_summary=bool(data.get("return_to_summary", False)),
        )
    )


def clear_content_session(*, workspace_root: Path) -> Result[None, ReleaseError]:
    path = content_session_path(workspace_root=workspace_root)
    if not path.exists():
        return Ok(None)
    try:
        path.unlink()
    except OSError as exc:
        return Err(
            ReleaseError(
                kind="repo_failed",
                message=f"failed to delete release session: {exc}",
                hint=str(path),
            )
        )
    return Ok(None)
