from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from typing import Literal, cast

from ms.cli.selector import SelectorOption, SelectorResult, select_one
from ms.core.result import Err, Ok, Result
from ms.output.console import ConsoleProtocol, Style
from ms.services.release.ci import fetch_green_head_shas
from ms.services.release.errors import ReleaseError
from ms.services.release.gh import current_user, list_recent_commits
from ms.services.release.model import ReleaseBump, ReleaseChannel
from ms.services.release.notes import load_external_notes_file
from ms.services.release.wizard_session import (
    AppReleaseSession,
    ContentReleaseSession,
    load_app_session,
    load_content_session,
    new_app_session,
    new_content_session,
    save_app_session,
    save_content_session,
)

ResumeChoice = Literal["resume", "new"]
NoteAction = Literal["keep", "clear"]


PermissionCheck = Callable[..., Result[None, ReleaseError]]


def select_channel(
    *, title: str, subtitle: str, initial_index: int, allow_back: bool
) -> SelectorResult[ReleaseChannel]:
    options = [
        SelectorOption(value="stable", label="stable", detail="Production release"),
        SelectorOption(value="beta", label="beta", detail="Pre-release channel"),
    ]
    return cast(
        SelectorResult[ReleaseChannel],
        select_one(
            title=title,
            subtitle=subtitle,
            options=options,
            initial_index=initial_index,
            allow_back=allow_back,
        ),
    )


def select_bump(
    *, title: str, subtitle: str, initial_index: int, allow_back: bool
) -> SelectorResult[ReleaseBump]:
    options = [
        SelectorOption(value="patch", label="patch", detail="Bug fixes and minor updates"),
        SelectorOption(value="minor", label="minor", detail="Feature release"),
        SelectorOption(value="major", label="major", detail="Breaking release"),
    ]
    return cast(
        SelectorResult[ReleaseBump],
        select_one(
            title=title,
            subtitle=subtitle,
            options=options,
            initial_index=initial_index,
            allow_back=allow_back,
        ),
    )


def select_resume_or_new(*, title: str, subtitle: str) -> SelectorResult[ResumeChoice]:
    options = [
        SelectorOption(value="resume", label="Resume", detail="Continue previous selections"),
        SelectorOption(value="new", label="Start new", detail="Discard previous selections"),
    ]
    return cast(
        SelectorResult[ResumeChoice],
        select_one(
            title=title,
            subtitle=subtitle,
            options=options,
            allow_back=False,
        ),
    )


def preflight_with_permission(
    *,
    workspace_root: Path,
    console: ConsoleProtocol,
    permission_check: PermissionCheck,
) -> Result[str, ReleaseError]:
    ok = permission_check(
        workspace_root=workspace_root,
        console=console,
        require_write=True,
    )
    if isinstance(ok, Err):
        return ok

    who = current_user(workspace_root=workspace_root)
    if isinstance(who, Err):
        return who
    return Ok(who.value.login)


def load_notes_snapshot(
    *,
    notes_file: Path | None,
) -> Result[tuple[str, str, str] | None, ReleaseError]:
    if notes_file is None:
        return Ok(None)

    notes = load_external_notes_file(path=notes_file)
    if isinstance(notes, Err):
        return notes

    return Ok(
        (
            str(notes.value.source_path.resolve()),
            notes.value.markdown,
            notes.value.sha256,
        )
    )


def notes_step_selector(
    *,
    has_notes: bool,
    notes_path: str | None,
    title: str,
    subtitle: str,
    clear_detail: str,
) -> SelectorResult[NoteAction]:
    options: list[SelectorOption[str]] = [
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

    return cast(
        SelectorResult[NoteAction],
        select_one(
            title=title,
            subtitle=subtitle,
            options=options,
            initial_index=0,
            allow_back=True,
        ),
    )


def print_notes_status(
    *,
    console: ConsoleProtocol,
    notes_markdown: str | None,
    notes_path: str | None,
    notes_sha256: str | None,
    auto_label: str,
) -> None:
    if notes_markdown is None:
        console.print(auto_label, Style.DIM)
        return

    digest = notes_sha256[:12] if notes_sha256 is not None else "n/a"
    source = notes_path or "(unknown source)"
    console.print(
        f"notes: attached from {source} ({len(notes_markdown)} bytes, sha256={digest})",
        Style.DIM,
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
    for c in commits_r.value:
        if green_shas is not None and c.sha not in green_shas:
            continue
        options.append(
            SelectorOption(
                value=c.sha,
                label=f"{c.short_sha}  {c.message}",
                detail=(c.date_utc or ""),
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
    loaded = load_app_session(workspace_root=workspace_root)
    if isinstance(loaded, Err):
        return loaded

    if loaded.value is not None:
        resume = select_resume_or_new(
            title="Resume App Release Session",
            subtitle="An unfinished app release session exists",
        )
        if resume.action == "cancel":
            return Err(ReleaseError(kind="invalid_input", message="release cancelled"))
        session = (
            loaded.value
            if resume.value == "resume"
            else new_app_session(created_by=created_by, notes_path=notes_file)
        )
    else:
        session = new_app_session(created_by=created_by, notes_path=notes_file)

    notes = load_notes_snapshot(notes_file=notes_file)
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
) -> Result[ContentReleaseSession, ReleaseError]:
    loaded = load_content_session(workspace_root=workspace_root)
    if isinstance(loaded, Err):
        return loaded

    if loaded.value is not None:
        resume = select_resume_or_new(
            title="Resume Content Release Session",
            subtitle="An unfinished content release session exists",
        )
        if resume.action == "cancel":
            return Err(ReleaseError(kind="invalid_input", message="release cancelled"))
        session = (
            loaded.value
            if resume.value == "resume"
            else new_content_session(created_by=created_by, notes_path=notes_file)
        )
    else:
        session = new_content_session(created_by=created_by, notes_path=notes_file)

    notes = load_notes_snapshot(notes_file=notes_file)
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
    *, workspace_root: Path, session: AppReleaseSession
) -> Result[AppReleaseSession, ReleaseError]:
    saved = save_app_session(workspace_root=workspace_root, session=session)
    if isinstance(saved, Err):
        return saved
    return Ok(session)


def save_content_state(
    *, workspace_root: Path, session: ContentReleaseSession
) -> Result[ContentReleaseSession, ReleaseError]:
    saved = save_content_session(workspace_root=workspace_root, session=session)
    if isinstance(saved, Err):
        return saved
    return Ok(session)
