from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal
from uuid import uuid4

from ms.core.result import Err, Ok, Result
from ms.core.structured import as_obj_list, as_str_dict, get_str
from ms.platform.files import atomic_write_text
from ms.release.domain.models import ReleaseBump, ReleaseChannel
from ms.release.errors import ReleaseError

SessionStep = Literal[
    "product",
    "channel",
    "bump",
    "tag",
    "sha",
    "notes",
    "summary",
    "confirm",
]

ContentSessionStep = Literal[
    "product",
    "channel",
    "bump",
    "repo",
    "tag",
    "notes",
    "summary",
    "confirm",
]


@dataclass(frozen=True, slots=True)
class AppReleaseSession:
    schema: Literal[2]
    release_id: str
    created_at: str
    created_by: str
    step: SessionStep
    product: Literal["app"]
    channel: ReleaseChannel | None
    bump: ReleaseBump | None
    tag: str | None
    version: str | None
    repo_ref: str
    repo_sha: str | None
    notes_path: str | None
    notes_markdown: str | None
    notes_sha256: str | None
    idx_channel: int
    idx_bump: int
    idx_sha: int
    idx_summary: int
    return_to_summary: bool


@dataclass(frozen=True, slots=True)
class ContentReleaseSession:
    schema: Literal[2]
    release_id: str
    created_at: str
    created_by: str
    step: ContentSessionStep
    product: Literal["content"]
    channel: ReleaseChannel | None
    bump: ReleaseBump | None
    tag: str | None
    repo_cursor: int
    repo_shas: tuple[tuple[str, str], ...]
    notes_path: str | None
    notes_markdown: str | None
    notes_sha256: str | None
    idx_channel: int
    idx_bump: int
    idx_repo: int
    idx_summary: int
    return_to_summary: bool


def _sessions_root(*, workspace_root: Path) -> Path:
    return workspace_root / ".ms" / "release" / "sessions"


def _session_path(*, workspace_root: Path) -> Path:
    return _sessions_root(workspace_root=workspace_root) / "app-release.json"


def _content_session_path(*, workspace_root: Path) -> Path:
    return _sessions_root(workspace_root=workspace_root) / "content-release.json"


def _parse_channel(value: str | None) -> ReleaseChannel | None:
    if value == "stable":
        return "stable"
    if value == "beta":
        return "beta"
    return None


def _parse_bump(value: str | None) -> ReleaseBump | None:
    if value == "major":
        return "major"
    if value == "minor":
        return "minor"
    if value == "patch":
        return "patch"
    return None


def _parse_app_step(value: str | None) -> SessionStep | None:
    if value == "product":
        return "product"
    if value == "channel":
        return "channel"
    if value == "bump":
        return "bump"
    if value == "tag":
        return "tag"
    if value == "sha":
        return "sha"
    if value == "notes":
        return "notes"
    if value == "summary":
        return "summary"
    if value == "confirm":
        return "confirm"
    return None


def _parse_content_step(value: str | None) -> ContentSessionStep | None:
    if value == "product":
        return "product"
    if value == "channel":
        return "channel"
    if value == "bump":
        return "bump"
    if value == "repo":
        return "repo"
    if value == "tag":
        return "tag"
    if value == "notes":
        return "notes"
    if value == "summary":
        return "summary"
    if value == "confirm":
        return "confirm"
    return None


def _get_int(record: dict[str, object], *, name: str, default: int) -> int:
    value = record.get(name)
    return value if isinstance(value, int) else default


def new_app_session(*, created_by: str, notes_path: Path | None) -> AppReleaseSession:
    now = datetime.now(tz=UTC).isoformat()
    return AppReleaseSession(
        schema=2,
        release_id=f"app-{uuid4().hex[:12]}",
        created_at=now,
        created_by=created_by,
        step="product",
        product="app",
        channel=None,
        bump=None,
        tag=None,
        version=None,
        repo_ref="main",
        repo_sha=None,
        notes_path=(str(notes_path) if notes_path is not None else None),
        notes_markdown=None,
        notes_sha256=None,
        idx_channel=0,
        idx_bump=0,
        idx_sha=0,
        idx_summary=0,
        return_to_summary=False,
    )


def new_content_session(*, created_by: str, notes_path: Path | None) -> ContentReleaseSession:
    now = datetime.now(tz=UTC).isoformat()
    return ContentReleaseSession(
        schema=2,
        release_id=f"content-{uuid4().hex[:12]}",
        created_at=now,
        created_by=created_by,
        step="product",
        product="content",
        channel=None,
        bump=None,
        tag=None,
        repo_cursor=0,
        repo_shas=(),
        notes_path=(str(notes_path) if notes_path is not None else None),
        notes_markdown=None,
        notes_sha256=None,
        idx_channel=0,
        idx_bump=0,
        idx_repo=0,
        idx_summary=0,
        return_to_summary=False,
    )


def save_app_session(
    *, workspace_root: Path, session: AppReleaseSession
) -> Result[None, ReleaseError]:
    path = _session_path(workspace_root=workspace_root)
    payload: dict[str, object] = {
        "schema": 2,
        "release_id": session.release_id,
        "created_at": session.created_at,
        "created_by": session.created_by,
        "step": session.step,
        "product": session.product,
        "channel": session.channel,
        "bump": session.bump,
        "tag": session.tag,
        "version": session.version,
        "repo_ref": session.repo_ref,
        "repo_sha": session.repo_sha,
        "notes_path": session.notes_path,
        "notes_markdown": session.notes_markdown,
        "notes_sha256": session.notes_sha256,
        "idx_channel": session.idx_channel,
        "idx_bump": session.idx_bump,
        "idx_sha": session.idx_sha,
        "idx_summary": session.idx_summary,
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


def load_app_session(*, workspace_root: Path) -> Result[AppReleaseSession | None, ReleaseError]:
    path = _session_path(workspace_root=workspace_root)
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

    if data.get("schema") != 2:
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
    step = _parse_app_step(get_str(data, "step"))
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
            schema=2,
            release_id=release_id,
            created_at=created_at,
            created_by=created_by,
            step=step,
            product="app",
            channel=_parse_channel(get_str(data, "channel")),
            bump=_parse_bump(get_str(data, "bump")),
            tag=get_str(data, "tag"),
            version=get_str(data, "version"),
            repo_ref=repo_ref,
            repo_sha=get_str(data, "repo_sha"),
            notes_path=get_str(data, "notes_path"),
            notes_markdown=get_str(data, "notes_markdown"),
            notes_sha256=get_str(data, "notes_sha256"),
            idx_channel=_get_int(data, name="idx_channel", default=0),
            idx_bump=_get_int(data, name="idx_bump", default=0),
            idx_sha=_get_int(data, name="idx_sha", default=0),
            idx_summary=_get_int(data, name="idx_summary", default=0),
            return_to_summary=bool(data.get("return_to_summary", False)),
        )
    )


def clear_app_session(*, workspace_root: Path) -> Result[None, ReleaseError]:
    path = _session_path(workspace_root=workspace_root)
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


def save_content_session(
    *, workspace_root: Path, session: ContentReleaseSession
) -> Result[None, ReleaseError]:
    path = _content_session_path(workspace_root=workspace_root)
    payload: dict[str, object] = {
        "schema": 2,
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
    path = _content_session_path(workspace_root=workspace_root)
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

    if data.get("schema") != 2:
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
    step = _parse_content_step(get_str(data, "step"))
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
            schema=2,
            release_id=release_id,
            created_at=created_at,
            created_by=created_by,
            step=step,
            product="content",
            channel=_parse_channel(get_str(data, "channel")),
            bump=_parse_bump(get_str(data, "bump")),
            tag=get_str(data, "tag"),
            repo_cursor=max(0, repo_cursor_obj),
            repo_shas=tuple(parsed_repo_shas),
            notes_path=get_str(data, "notes_path"),
            notes_markdown=get_str(data, "notes_markdown"),
            notes_sha256=get_str(data, "notes_sha256"),
            idx_channel=_get_int(data, name="idx_channel", default=0),
            idx_bump=_get_int(data, name="idx_bump", default=0),
            idx_repo=_get_int(data, name="idx_repo", default=0),
            idx_summary=_get_int(data, name="idx_summary", default=0),
            return_to_summary=bool(data.get("return_to_summary", False)),
        )
    )


def clear_content_session(*, workspace_root: Path) -> Result[None, ReleaseError]:
    path = _content_session_path(workspace_root=workspace_root)
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


__all__ = [
    "AppReleaseSession",
    "ContentReleaseSession",
    "ContentSessionStep",
    "SessionStep",
    "clear_app_session",
    "clear_content_session",
    "load_app_session",
    "load_content_session",
    "new_app_session",
    "new_content_session",
    "save_app_session",
    "save_content_session",
]
