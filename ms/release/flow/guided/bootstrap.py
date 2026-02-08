from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Literal, Protocol

from ms.core.result import Err, Ok, Result
from ms.output.console import ConsoleProtocol
from ms.release.domain.notes import ExternalNotesSnapshot
from ms.release.errors import ReleaseError

from .selection import Selection
from .sessions import (
    AppReleaseSession,
    ContentReleaseSession,
)

ResumeChoice = Literal["resume", "new"]


class PermissionCheck(Protocol):
    def __call__(
        self,
        *,
        workspace_root: Path,
        console: ConsoleProtocol,
        require_write: bool,
    ) -> Result[None, ReleaseError]: ...


class BootstrapDeps(Protocol):
    def current_user_login(self, *, workspace_root: Path) -> Result[str, ReleaseError]: ...

    def load_external_notes_file(
        self, *, path: Path
    ) -> Result[ExternalNotesSnapshot, ReleaseError]: ...

    def load_app_session(
        self, *, workspace_root: Path
    ) -> Result[AppReleaseSession | None, ReleaseError]: ...

    def load_content_session(
        self, *, workspace_root: Path
    ) -> Result[ContentReleaseSession | None, ReleaseError]: ...

    def save_app_session(
        self, *, workspace_root: Path, session: AppReleaseSession
    ) -> Result[None, ReleaseError]: ...

    def save_content_session(
        self, *, workspace_root: Path, session: ContentReleaseSession
    ) -> Result[None, ReleaseError]: ...

    def new_app_session(self, *, created_by: str, notes_path: Path | None) -> AppReleaseSession: ...

    def new_content_session(
        self, *, created_by: str, notes_path: Path | None
    ) -> ContentReleaseSession: ...

    def select_resume_or_new(self, *, title: str, subtitle: str) -> Selection[ResumeChoice]: ...


def preflight_with_permission(
    *,
    workspace_root: Path,
    console: ConsoleProtocol,
    permission_check: PermissionCheck,
    deps: BootstrapDeps,
) -> Result[str, ReleaseError]:
    ok = permission_check(
        workspace_root=workspace_root,
        console=console,
        require_write=True,
    )
    if isinstance(ok, Err):
        return ok

    who = deps.current_user_login(workspace_root=workspace_root)
    if isinstance(who, Err):
        return who
    return Ok(who.value)


def load_notes_snapshot(
    *,
    notes_file: Path | None,
    deps: BootstrapDeps,
) -> Result[tuple[str, str, str] | None, ReleaseError]:
    if notes_file is None:
        return Ok(None)

    notes = deps.load_external_notes_file(path=notes_file)
    if isinstance(notes, Err):
        return notes

    return Ok(
        (
            str(notes.value.source_path.resolve()),
            notes.value.markdown,
            notes.value.sha256,
        )
    )


def bootstrap_app_session(
    *,
    workspace_root: Path,
    created_by: str,
    notes_file: Path | None,
    deps: BootstrapDeps,
) -> Result[AppReleaseSession, ReleaseError]:
    loaded = deps.load_app_session(workspace_root=workspace_root)
    if isinstance(loaded, Err):
        return loaded

    if loaded.value is not None:
        resume = deps.select_resume_or_new(
            title="Resume App Release Session",
            subtitle="An unfinished app release session exists",
        )
        if resume.action == "cancel":
            return Err(ReleaseError(kind="invalid_input", message="release cancelled"))
        session = (
            loaded.value
            if resume.value == "resume"
            else deps.new_app_session(created_by=created_by, notes_path=notes_file)
        )
    else:
        session = deps.new_app_session(created_by=created_by, notes_path=notes_file)

    notes = load_notes_snapshot(notes_file=notes_file, deps=deps)
    if isinstance(notes, Err):
        return notes
    if notes.value is not None:
        notes_path, notes_markdown, notes_sha256 = notes.value
        session = replace(
            session,
            notes_path=notes_path,
            notes_markdown=notes_markdown,
            notes_sha256=notes_sha256,
        )

    return Ok(session)


def bootstrap_content_session(
    *,
    workspace_root: Path,
    created_by: str,
    notes_file: Path | None,
    deps: BootstrapDeps,
) -> Result[ContentReleaseSession, ReleaseError]:
    loaded = deps.load_content_session(workspace_root=workspace_root)
    if isinstance(loaded, Err):
        return loaded

    if loaded.value is not None:
        resume = deps.select_resume_or_new(
            title="Resume Content Release Session",
            subtitle="An unfinished content release session exists",
        )
        if resume.action == "cancel":
            return Err(ReleaseError(kind="invalid_input", message="release cancelled"))
        session = (
            loaded.value
            if resume.value == "resume"
            else deps.new_content_session(created_by=created_by, notes_path=notes_file)
        )
    else:
        session = deps.new_content_session(created_by=created_by, notes_path=notes_file)

    notes = load_notes_snapshot(notes_file=notes_file, deps=deps)
    if isinstance(notes, Err):
        return notes
    if notes.value is not None:
        notes_path, notes_markdown, notes_sha256 = notes.value
        session = replace(
            session,
            notes_path=notes_path,
            notes_markdown=notes_markdown,
            notes_sha256=notes_sha256,
        )

    return Ok(session)


def save_app_state(
    *,
    workspace_root: Path,
    session: AppReleaseSession,
    deps: BootstrapDeps,
) -> Result[AppReleaseSession, ReleaseError]:
    saved = deps.save_app_session(workspace_root=workspace_root, session=session)
    if isinstance(saved, Err):
        return saved
    return Ok(session)


def save_content_state(
    *,
    workspace_root: Path,
    session: ContentReleaseSession,
    deps: BootstrapDeps,
) -> Result[ContentReleaseSession, ReleaseError]:
    saved = deps.save_content_session(workspace_root=workspace_root, session=session)
    if isinstance(saved, Err):
        return saved
    return Ok(session)
