from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal, cast
from uuid import uuid4

from ms.core.result import Err, Ok, Result
from ms.core.structured import as_str_dict, get_str
from ms.platform.files import atomic_write_text
from ms.services.release.errors import ReleaseError
from ms.services.release.model import ReleaseBump, ReleaseChannel

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
    except OSError as e:
        return Err(
            ReleaseError(
                kind="dist_repo_failed",
                message=f"failed to write release session: {e}",
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
        obj: object = json.loads(text)
    except (OSError, json.JSONDecodeError) as e:
        return Err(
            ReleaseError(
                kind="invalid_input",
                message=f"failed to load release session: {e}",
                hint=str(path),
            )
        )

    d = as_str_dict(obj)
    if d is None:
        return Err(
            ReleaseError(
                kind="invalid_input",
                message="invalid release session format",
                hint=str(path),
            )
        )

    schema = d.get("schema")
    if schema != 2:
        return Err(
            ReleaseError(
                kind="invalid_input",
                message=f"unsupported release session schema: {schema}",
                hint=str(path),
            )
        )

    release_id = get_str(d, "release_id")
    created_at = get_str(d, "created_at")
    created_by = get_str(d, "created_by")
    step = get_str(d, "step")
    product = get_str(d, "product")
    repo_ref = get_str(d, "repo_ref")

    if (
        release_id is None
        or created_at is None
        or created_by is None
        or step not in {"product", "channel", "bump", "tag", "sha", "notes", "summary", "confirm"}
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

    channel_s = get_str(d, "channel")
    channel: ReleaseChannel | None
    channel = cast(ReleaseChannel, channel_s) if channel_s in {"stable", "beta"} else None

    bump_s = get_str(d, "bump")
    bump: ReleaseBump | None
    bump = cast(ReleaseBump, bump_s) if bump_s in {"major", "minor", "patch"} else None

    step_value = cast(SessionStep, step)

    def get_int(name: str, default: int) -> int:
        v = d.get(name)
        return v if isinstance(v, int) else default

    return Ok(
        AppReleaseSession(
            schema=2,
            release_id=release_id,
            created_at=created_at,
            created_by=created_by,
            step=step_value,
            product="app",
            channel=channel,
            bump=bump,
            tag=get_str(d, "tag"),
            version=get_str(d, "version"),
            repo_ref=repo_ref,
            repo_sha=get_str(d, "repo_sha"),
            notes_path=get_str(d, "notes_path"),
            notes_markdown=get_str(d, "notes_markdown"),
            notes_sha256=get_str(d, "notes_sha256"),
            idx_channel=get_int("idx_channel", 0),
            idx_bump=get_int("idx_bump", 0),
            idx_sha=get_int("idx_sha", 0),
            idx_summary=get_int("idx_summary", 0),
            return_to_summary=bool(d.get("return_to_summary", False)),
        )
    )


def clear_app_session(*, workspace_root: Path) -> Result[None, ReleaseError]:
    path = _session_path(workspace_root=workspace_root)
    if not path.exists():
        return Ok(None)
    try:
        path.unlink()
    except OSError as e:
        return Err(
            ReleaseError(
                kind="dist_repo_failed",
                message=f"failed to delete release session: {e}",
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
    except OSError as e:
        return Err(
            ReleaseError(
                kind="dist_repo_failed",
                message=f"failed to write release session: {e}",
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
        obj: object = json.loads(text)
    except (OSError, json.JSONDecodeError) as e:
        return Err(
            ReleaseError(
                kind="invalid_input",
                message=f"failed to load release session: {e}",
                hint=str(path),
            )
        )

    d = as_str_dict(obj)
    if d is None:
        return Err(
            ReleaseError(
                kind="invalid_input",
                message="invalid release session format",
                hint=str(path),
            )
        )

    schema = d.get("schema")
    if schema != 2:
        return Err(
            ReleaseError(
                kind="invalid_input",
                message=f"unsupported release session schema: {schema}",
                hint=str(path),
            )
        )

    release_id = get_str(d, "release_id")
    created_at = get_str(d, "created_at")
    created_by = get_str(d, "created_by")
    step = get_str(d, "step")
    product = get_str(d, "product")
    repo_cursor_obj = d.get("repo_cursor")

    if (
        release_id is None
        or created_at is None
        or created_by is None
        or step not in {"product", "channel", "bump", "repo", "tag", "notes", "summary", "confirm"}
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

    channel_s = get_str(d, "channel")
    channel: ReleaseChannel | None
    channel = cast(ReleaseChannel, channel_s) if channel_s in {"stable", "beta"} else None

    bump_s = get_str(d, "bump")
    bump: ReleaseBump | None
    bump = cast(ReleaseBump, bump_s) if bump_s in {"major", "minor", "patch"} else None

    repo_shas_raw_obj = d.get("repo_shas")
    parsed_repo_shas: list[tuple[str, str]] = []
    if isinstance(repo_shas_raw_obj, list):
        repo_shas_raw = cast(list[object], repo_shas_raw_obj)
        for item in repo_shas_raw:
            row = as_str_dict(item)
            if row is None:
                continue
            rid = get_str(row, "id")
            sha = get_str(row, "sha")
            if rid is None or sha is None:
                continue
            parsed_repo_shas.append((rid, sha))

    step_value = cast(ContentSessionStep, step)

    def get_int(name: str, default: int) -> int:
        v = d.get(name)
        return v if isinstance(v, int) else default

    return Ok(
        ContentReleaseSession(
            schema=2,
            release_id=release_id,
            created_at=created_at,
            created_by=created_by,
            step=step_value,
            product="content",
            channel=channel,
            bump=bump,
            tag=get_str(d, "tag"),
            repo_cursor=max(0, repo_cursor_obj),
            repo_shas=tuple(parsed_repo_shas),
            notes_path=get_str(d, "notes_path"),
            notes_markdown=get_str(d, "notes_markdown"),
            notes_sha256=get_str(d, "notes_sha256"),
            idx_channel=get_int("idx_channel", 0),
            idx_bump=get_int("idx_bump", 0),
            idx_repo=get_int("idx_repo", 0),
            idx_summary=get_int("idx_summary", 0),
            return_to_summary=bool(d.get("return_to_summary", False)),
        )
    )


def clear_content_session(*, workspace_root: Path) -> Result[None, ReleaseError]:
    path = _content_session_path(workspace_root=workspace_root)
    if not path.exists():
        return Ok(None)
    try:
        path.unlink()
    except OSError as e:
        return Err(
            ReleaseError(
                kind="dist_repo_failed",
                message=f"failed to delete release session: {e}",
                hint=str(path),
            )
        )
    return Ok(None)
