from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from ms.cli.selector import SelectorResult
from ms.core.result import Result
from ms.output.console import ConsoleProtocol
from ms.release.domain.models import ReleaseBump, ReleaseChannel
from ms.release.errors import ReleaseError
from ms.release.flow.guided.sessions import AppReleaseSession, ContentReleaseSession

from .release_guided_bootstrap import (
    bootstrap_app_session as _bootstrap_app_session,
)
from .release_guided_bootstrap import (
    bootstrap_content_session as _bootstrap_content_session,
)
from .release_guided_bootstrap import (
    preflight_with_permission as _preflight_with_permission,
)
from .release_guided_bootstrap import (
    save_app_state as _save_app_state,
)
from .release_guided_bootstrap import (
    save_content_state as _save_content_state,
)
from .release_guided_green_commit import select_green_commit
from .release_guided_selectors import (
    NoteAction,
    notes_step_selector,
    print_notes_status,
    select_bump,
    select_channel,
    select_resume_or_new,
    to_guided_selection,
)


def preflight_with_permission(
    *,
    workspace_root: Path,
    console: ConsoleProtocol,
    permission_check: Callable[..., Result[None, ReleaseError]],
) -> Result[str, ReleaseError]:
    return _preflight_with_permission(
        workspace_root=workspace_root,
        console=console,
        permission_check=permission_check,
    )


def bootstrap_app_session(
    *,
    workspace_root: Path,
    created_by: str,
    notes_file: Path | None,
) -> Result[AppReleaseSession, ReleaseError]:
    return _bootstrap_app_session(
        workspace_root=workspace_root,
        created_by=created_by,
        notes_file=notes_file,
    )


def bootstrap_content_session(
    *,
    workspace_root: Path,
    created_by: str,
    notes_file: Path | None,
) -> Result[ContentReleaseSession, ReleaseError]:
    return _bootstrap_content_session(
        workspace_root=workspace_root,
        created_by=created_by,
        notes_file=notes_file,
    )


def save_app_state(
    *, workspace_root: Path, session: AppReleaseSession
) -> Result[AppReleaseSession, ReleaseError]:
    return _save_app_state(workspace_root=workspace_root, session=session)


def save_content_state(
    *, workspace_root: Path, session: ContentReleaseSession
) -> Result[ContentReleaseSession, ReleaseError]:
    return _save_content_state(workspace_root=workspace_root, session=session)


__all__ = [
    "NoteAction",
    "SelectorResult",
    "bootstrap_app_session",
    "bootstrap_content_session",
    "notes_step_selector",
    "preflight_with_permission",
    "print_notes_status",
    "save_app_state",
    "save_content_state",
    "select_bump",
    "select_channel",
    "select_green_commit",
    "select_resume_or_new",
    "to_guided_selection",
    "ReleaseBump",
    "ReleaseChannel",
]
