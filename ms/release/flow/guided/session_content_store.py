from __future__ import annotations

from dataclasses import asdict
from pathlib import Path

from ms.core.result import Err, Ok, Result
from ms.core.structured import as_obj_list, as_str_dict, get_str
from ms.release.errors import ReleaseError

from .session_models import ContentReleaseSession
from .session_parse import get_int, parse_bump, parse_channel, parse_content_step
from .session_paths import content_session_path
from .session_store import clear_session, read_session, write_session


def save_content_session(
    *, workspace_root: Path, session: ContentReleaseSession
) -> Result[None, ReleaseError]:
    payload = asdict(session)
    payload["repo_shas"] = [{"id": repo_id, "sha": sha} for repo_id, sha in session.repo_shas]
    return write_session(
        path=content_session_path(workspace_root=workspace_root),
        payload=payload,
    )


def load_content_session(
    *, workspace_root: Path
) -> Result[ContentReleaseSession | None, ReleaseError]:
    path = content_session_path(workspace_root=workspace_root)
    loaded = read_session(path=path)
    if isinstance(loaded, Err):
        return loaded
    if loaded.value is None:
        return Ok(None)
    data = loaded.value

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
    return clear_session(path=content_session_path(workspace_root=workspace_root))
