from __future__ import annotations

from dataclasses import dataclass, field
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
class SessionCursor:
    """UI navigation state, kept out of the business release plan."""

    channel: int = 0
    bump: int = 0
    sha: int = 0
    repo: int = 0
    summary: int = 0
    candidates: int = 0
    return_to_summary: bool = False


@dataclass(frozen=True, slots=True)
class AppReleaseSession:
    schema: Literal[4]
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
    cursor: SessionCursor = field(default_factory=SessionCursor)
    pending_kind: str | None = None
    pending_request_id: str | None = None
    pending_repo: str | None = None
    pending_workflow: str | None = None
    pending_tag: str | None = None
    pending_source_sha: str | None = None
    pending_tooling_sha: str | None = None
    pending_at: str | None = None


@dataclass(frozen=True, slots=True)
class ContentReleaseSession:
    schema: Literal[4]
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
    cursor: SessionCursor = field(default_factory=SessionCursor)
    pending_kind: str | None = None
    pending_request_id: str | None = None
    pending_repo: str | None = None
    pending_workflow: str | None = None
    pending_tag: str | None = None
    pending_source_sha: str | None = None
    pending_tooling_sha: str | None = None
    pending_at: str | None = None


def new_app_session(*, created_by: str, notes_path: Path | None) -> AppReleaseSession:
    now = datetime.now(tz=UTC).isoformat()
    return AppReleaseSession(
        schema=4,
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
    )


def new_content_session(*, created_by: str, notes_path: Path | None) -> ContentReleaseSession:
    now = datetime.now(tz=UTC).isoformat()
    return ContentReleaseSession(
        schema=4,
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
    )
