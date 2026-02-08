from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from ms.core.result import Err, Ok, Result
from ms.output.console import ConsoleProtocol
from ms.release.domain.notes import ExternalNotesSnapshot
from ms.release.errors import ReleaseError
from ms.release.flow.guided.bootstrap import (
    BootstrapDeps,
    ResumeChoice,
)
from ms.release.flow.guided.bootstrap import (
    bootstrap_app_session as bootstrap_app_session_flow,
)
from ms.release.flow.guided.bootstrap import (
    bootstrap_content_session as bootstrap_content_session_flow,
)
from ms.release.flow.guided.bootstrap import (
    preflight_with_permission as preflight_with_permission_flow,
)
from ms.release.flow.guided.bootstrap import (
    save_app_state as save_app_state_flow,
)
from ms.release.flow.guided.bootstrap import (
    save_content_state as save_content_state_flow,
)
from ms.release.flow.guided.selection import Selection
from ms.release.flow.guided.sessions import (
    AppReleaseSession,
    ContentReleaseSession,
    load_app_session,
    load_content_session,
    new_app_session,
    new_content_session,
    save_app_session,
    save_content_session,
)
from ms.release.infra.artifacts.notes_writer import load_external_notes_file
from ms.release.infra.github.client import current_user

from .release_guided_selectors import select_resume_or_new, to_guided_selection


class _BootstrapDeps(BootstrapDeps):
    def current_user_login(self, *, workspace_root: Path) -> Result[str, ReleaseError]:
        who = current_user(workspace_root=workspace_root)
        if isinstance(who, Err):
            return who
        return Ok(who.value.login)

    def load_external_notes_file(
        self, *, path: Path
    ) -> Result[ExternalNotesSnapshot, ReleaseError]:
        return load_external_notes_file(path=path)

    def load_app_session(
        self, *, workspace_root: Path
    ) -> Result[AppReleaseSession | None, ReleaseError]:
        return load_app_session(workspace_root=workspace_root)

    def load_content_session(
        self, *, workspace_root: Path
    ) -> Result[ContentReleaseSession | None, ReleaseError]:
        return load_content_session(workspace_root=workspace_root)

    def save_app_session(
        self, *, workspace_root: Path, session: AppReleaseSession
    ) -> Result[None, ReleaseError]:
        return save_app_session(workspace_root=workspace_root, session=session)

    def save_content_session(
        self, *, workspace_root: Path, session: ContentReleaseSession
    ) -> Result[None, ReleaseError]:
        return save_content_session(workspace_root=workspace_root, session=session)

    def new_app_session(self, *, created_by: str, notes_path: Path | None) -> AppReleaseSession:
        return new_app_session(created_by=created_by, notes_path=notes_path)

    def new_content_session(
        self, *, created_by: str, notes_path: Path | None
    ) -> ContentReleaseSession:
        return new_content_session(created_by=created_by, notes_path=notes_path)

    def select_resume_or_new(self, *, title: str, subtitle: str) -> Selection[ResumeChoice]:
        return to_guided_selection(select_resume_or_new(title=title, subtitle=subtitle))


def preflight_with_permission(
    *,
    workspace_root: Path,
    console: ConsoleProtocol,
    permission_check: Callable[..., Result[None, ReleaseError]],
) -> Result[str, ReleaseError]:
    return preflight_with_permission_flow(
        workspace_root=workspace_root,
        console=console,
        permission_check=permission_check,
        deps=_BootstrapDeps(),
    )


def bootstrap_app_session(
    *,
    workspace_root: Path,
    created_by: str,
    notes_file: Path | None,
) -> Result[AppReleaseSession, ReleaseError]:
    return bootstrap_app_session_flow(
        workspace_root=workspace_root,
        created_by=created_by,
        notes_file=notes_file,
        deps=_BootstrapDeps(),
    )


def bootstrap_content_session(
    *,
    workspace_root: Path,
    created_by: str,
    notes_file: Path | None,
) -> Result[ContentReleaseSession, ReleaseError]:
    return bootstrap_content_session_flow(
        workspace_root=workspace_root,
        created_by=created_by,
        notes_file=notes_file,
        deps=_BootstrapDeps(),
    )


def save_app_state(
    *, workspace_root: Path, session: AppReleaseSession
) -> Result[AppReleaseSession, ReleaseError]:
    return save_app_state_flow(
        workspace_root=workspace_root,
        session=session,
        deps=_BootstrapDeps(),
    )


def save_content_state(
    *, workspace_root: Path, session: ContentReleaseSession
) -> Result[ContentReleaseSession, ReleaseError]:
    return save_content_state_flow(
        workspace_root=workspace_root,
        session=session,
        deps=_BootstrapDeps(),
    )
