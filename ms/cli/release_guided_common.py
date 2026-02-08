from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Literal

from ms.cli.selector import SelectorOption, SelectorResult, select_one
from ms.core.result import Err, Ok, Result
from ms.output.console import ConsoleProtocol
from ms.release.domain.models import ReleaseBump, ReleaseChannel
from ms.release.errors import ReleaseError
from ms.release.flow.guided.bootstrap import (
    bootstrap_app_session as bootstrap_app_session_flow,
)
from ms.release.flow.guided.bootstrap import (
    bootstrap_content_session as bootstrap_content_session_flow,
)
from ms.release.flow.guided.bootstrap import (
    load_notes_snapshot as load_notes_snapshot_flow,
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
from ms.release.infra.github.ci import fetch_green_head_shas
from ms.release.infra.github.client import current_user, list_recent_commits
from ms.release.view.guided_console import print_notes_status as print_notes_status_view

ResumeChoice = Literal["resume", "new"]
NoteAction = Literal["keep", "clear"]


PermissionCheck = Callable[..., Result[None, ReleaseError]]


def to_guided_selection[T](choice: SelectorResult[T]) -> Selection[T]:
    return Selection(action=choice.action, value=choice.value, index=choice.index)


def select_channel(
    *, title: str, subtitle: str, initial_index: int, allow_back: bool
) -> SelectorResult[ReleaseChannel]:
    options: list[SelectorOption[ReleaseChannel]] = [
        SelectorOption(value="stable", label="stable", detail="Production release"),
        SelectorOption(value="beta", label="beta", detail="Pre-release channel"),
    ]
    return select_one(
        title=title,
        subtitle=subtitle,
        options=options,
        initial_index=initial_index,
        allow_back=allow_back,
    )


def select_bump(
    *, title: str, subtitle: str, initial_index: int, allow_back: bool
) -> SelectorResult[ReleaseBump]:
    options: list[SelectorOption[ReleaseBump]] = [
        SelectorOption(value="patch", label="patch", detail="Bug fixes and minor updates"),
        SelectorOption(value="minor", label="minor", detail="Feature release"),
        SelectorOption(value="major", label="major", detail="Breaking release"),
    ]
    return select_one(
        title=title,
        subtitle=subtitle,
        options=options,
        initial_index=initial_index,
        allow_back=allow_back,
    )


def select_resume_or_new(*, title: str, subtitle: str) -> SelectorResult[ResumeChoice]:
    options: list[SelectorOption[ResumeChoice]] = [
        SelectorOption(value="resume", label="Resume", detail="Continue previous selections"),
        SelectorOption(value="new", label="Start new", detail="Discard previous selections"),
    ]
    return select_one(
        title=title,
        subtitle=subtitle,
        options=options,
        allow_back=False,
    )


def preflight_with_permission(
    *,
    workspace_root: Path,
    console: ConsoleProtocol,
    permission_check: PermissionCheck,
) -> Result[str, ReleaseError]:
    return preflight_with_permission_flow(
        workspace_root=workspace_root,
        console=console,
        permission_check=permission_check,
        current_user_fn=current_user,
    )


def load_notes_snapshot(
    *,
    notes_file: Path | None,
) -> Result[tuple[str, str, str] | None, ReleaseError]:
    return load_notes_snapshot_flow(
        notes_file=notes_file,
        load_external_notes_file_fn=load_external_notes_file,
    )


def notes_step_selector(
    *,
    has_notes: bool,
    notes_path: str | None,
    title: str,
    subtitle: str,
    clear_detail: str,
) -> SelectorResult[NoteAction]:
    options: list[SelectorOption[NoteAction]] = [
        SelectorOption(
            value="keep",
            label=("Keep notes" if has_notes else "No notes configured"),
            detail=(notes_path if notes_path is not None else "Provide --notes-file to set notes"),
        ),
    ]
    if has_notes:
        options.append(
            SelectorOption(
                value="clear",
                label="Remove notes",
                detail=clear_detail,
            )
        )

    return select_one(
        title=title,
        subtitle=subtitle,
        options=options,
        initial_index=0,
        allow_back=True,
    )


def print_notes_status(
    *,
    console: ConsoleProtocol,
    notes_markdown: str | None,
    notes_path: str | None,
    notes_sha256: str | None,
    auto_label: str,
) -> None:
    print_notes_status_view(
        console=console,
        notes_markdown=notes_markdown,
        notes_path=notes_path,
        notes_sha256=notes_sha256,
        auto_label=auto_label,
    )


def select_green_commit(
    *,
    workspace_root: Path,
    repo_slug: str,
    ref: str,
    workflow_file: str | None,
    title: str,
    subtitle: str,
    current_sha: str | None,
    initial_index: int,
    allow_back: bool,
) -> Result[SelectorResult[str], ReleaseError]:
    commits_r = list_recent_commits(
        workspace_root=workspace_root,
        repo=repo_slug,
        ref=ref,
        limit=40,
    )
    if isinstance(commits_r, Err):
        return commits_r

    green_shas: set[str] | None = None
    if workflow_file is not None:
        green_r = fetch_green_head_shas(
            workspace_root=workspace_root,
            repo=repo_slug,
            workflow_file=workflow_file,
            branch=ref,
            limit=200,
        )
        if isinstance(green_r, Err):
            return green_r
        green_shas = set(green_r.value.green_head_shas)

    options: list[SelectorOption[str]] = []
    for commit in commits_r.value:
        if green_shas is not None and commit.sha not in green_shas:
            continue
        options.append(
            SelectorOption(
                value=commit.sha,
                label=f"{commit.short_sha}  {commit.message}",
                detail=(commit.date_utc or ""),
            )
        )

    if not options:
        return Err(
            ReleaseError(
                kind="ci_not_green",
                message=f"no green commits available for {repo_slug}@{ref}",
                hint="Wait for CI green or investigate failed runs.",
            )
        )

    idx = max(0, min(initial_index, len(options) - 1))
    if current_sha is not None:
        for i, opt in enumerate(options):
            if opt.value == current_sha:
                idx = i
                break

    return Ok(
        select_one(
            title=title,
            subtitle=subtitle,
            options=options,
            initial_index=idx,
            allow_back=allow_back,
        )
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
        load_app_session_fn=load_app_session,
        new_app_session_fn=new_app_session,
        select_resume_or_new_fn=select_resume_or_new,
        load_notes_snapshot_fn=load_notes_snapshot,
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
        load_content_session_fn=load_content_session,
        new_content_session_fn=new_content_session,
        select_resume_or_new_fn=select_resume_or_new,
        load_notes_snapshot_fn=load_notes_snapshot,
    )


def save_app_state(
    *, workspace_root: Path, session: AppReleaseSession
) -> Result[AppReleaseSession, ReleaseError]:
    return save_app_state_flow(
        workspace_root=workspace_root,
        session=session,
        save_app_session_fn=save_app_session,
    )


def save_content_state(
    *, workspace_root: Path, session: ContentReleaseSession
) -> Result[ContentReleaseSession, ReleaseError]:
    return save_content_state_flow(
        workspace_root=workspace_root,
        session=session,
        save_content_session_fn=save_content_session,
    )
