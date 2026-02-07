from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from typing import Literal, Protocol

from ms.core.result import Err, Ok, Result
from ms.output.console import ConsoleProtocol
from ms.release.errors import ReleaseError

from .sessions import (
    AppReleaseSession,
    ContentReleaseSession,
)

ResumeChoice = Literal["resume", "new"]
PermissionCheck = Callable[..., Result[None, ReleaseError]]


class CurrentUserLike(Protocol):
    @property
    def login(self) -> str: ...


class ExternalNotesSnapshotLike(Protocol):
    @property
    def source_path(self) -> Path: ...

    @property
    def markdown(self) -> str: ...

    @property
    def sha256(self) -> str: ...


class ResumeSelectionLike(Protocol):
    @property
    def action(self) -> Literal["select", "cancel", "back"]: ...

    @property
    def value(self) -> ResumeChoice | None: ...


def preflight_with_permission[UserT: CurrentUserLike](
    *,
    workspace_root: Path,
    console: ConsoleProtocol,
    permission_check: PermissionCheck,
    current_user_fn: Callable[..., Result[UserT, ReleaseError]],
) -> Result[str, ReleaseError]:
    ok = permission_check(
        workspace_root=workspace_root,
        console=console,
        require_write=True,
    )
    if isinstance(ok, Err):
        return ok

    who = current_user_fn(workspace_root=workspace_root)
    if isinstance(who, Err):
        return who
    return Ok(who.value.login)


def load_notes_snapshot[NotesT: ExternalNotesSnapshotLike](
    *,
    notes_file: Path | None,
    load_external_notes_file_fn: Callable[..., Result[NotesT, ReleaseError]],
) -> Result[tuple[str, str, str] | None, ReleaseError]:
    if notes_file is None:
        return Ok(None)

    notes = load_external_notes_file_fn(path=notes_file)
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
    load_app_session_fn: Callable[..., Result[AppReleaseSession | None, ReleaseError]],
    new_app_session_fn: Callable[..., AppReleaseSession],
    select_resume_or_new_fn: Callable[..., ResumeSelectionLike],
    load_notes_snapshot_fn: Callable[..., Result[tuple[str, str, str] | None, ReleaseError]],
) -> Result[AppReleaseSession, ReleaseError]:
    loaded = load_app_session_fn(workspace_root=workspace_root)
    if isinstance(loaded, Err):
        return loaded

    if loaded.value is not None:
        resume = select_resume_or_new_fn(
            title="Resume App Release Session",
            subtitle="An unfinished app release session exists",
        )
        if resume.action == "cancel":
            return Err(ReleaseError(kind="invalid_input", message="release cancelled"))
        session = (
            loaded.value
            if resume.value == "resume"
            else new_app_session_fn(created_by=created_by, notes_path=notes_file)
        )
    else:
        session = new_app_session_fn(created_by=created_by, notes_path=notes_file)

    notes = load_notes_snapshot_fn(notes_file=notes_file)
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
    load_content_session_fn: Callable[..., Result[ContentReleaseSession | None, ReleaseError]],
    new_content_session_fn: Callable[..., ContentReleaseSession],
    select_resume_or_new_fn: Callable[..., ResumeSelectionLike],
    load_notes_snapshot_fn: Callable[..., Result[tuple[str, str, str] | None, ReleaseError]],
) -> Result[ContentReleaseSession, ReleaseError]:
    loaded = load_content_session_fn(workspace_root=workspace_root)
    if isinstance(loaded, Err):
        return loaded

    if loaded.value is not None:
        resume = select_resume_or_new_fn(
            title="Resume Content Release Session",
            subtitle="An unfinished content release session exists",
        )
        if resume.action == "cancel":
            return Err(ReleaseError(kind="invalid_input", message="release cancelled"))
        session = (
            loaded.value
            if resume.value == "resume"
            else new_content_session_fn(created_by=created_by, notes_path=notes_file)
        )
    else:
        session = new_content_session_fn(created_by=created_by, notes_path=notes_file)

    notes = load_notes_snapshot_fn(notes_file=notes_file)
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
    save_app_session_fn: Callable[..., Result[None, ReleaseError]],
) -> Result[AppReleaseSession, ReleaseError]:
    saved = save_app_session_fn(workspace_root=workspace_root, session=session)
    if isinstance(saved, Err):
        return saved
    return Ok(session)


def save_content_state(
    *,
    workspace_root: Path,
    session: ContentReleaseSession,
    save_content_session_fn: Callable[..., Result[None, ReleaseError]],
) -> Result[ContentReleaseSession, ReleaseError]:
    saved = save_content_session_fn(workspace_root=workspace_root, session=session)
    if isinstance(saved, Err):
        return saved
    return Ok(session)
