from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal
from uuid import uuid4

from ms.release.domain.models import ReleaseBump, ReleaseChannel

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
    "bom",
    "tag",
    "notes",
    "summary",
    "candidates",
    "confirm",
]


@dataclass(frozen=True, slots=True)
class AppReleaseSession:
    schema: Literal[3]
    release_id: str
    created_at: str
    created_by: str
    step: SessionStep
    product: Literal["app"]
    channel: ReleaseChannel | None
    bump: ReleaseBump | None
    tag: str | None
    version: str | None
    tooling_sha: str | None
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
    schema: Literal[3]
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
    idx_candidates: int
    return_to_summary: bool


def new_app_session(*, created_by: str, notes_path: Path | None) -> AppReleaseSession:
    now = datetime.now(tz=UTC).isoformat()
    return AppReleaseSession(
        schema=3,
        release_id=f"app-{uuid4().hex[:12]}",
        created_at=now,
        created_by=created_by,
        step="product",
        product="app",
        channel=None,
        bump=None,
        tag=None,
        version=None,
        tooling_sha=None,
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
        schema=3,
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
        idx_candidates=0,
        return_to_summary=False,
    )
