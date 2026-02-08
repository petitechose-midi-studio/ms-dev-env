from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Protocol

from ms.core.result import Err, Ok, Result
from ms.output.console import ConsoleProtocol, Style
from ms.release.domain import config
from ms.release.domain.notes import AppPublishNotes
from ms.release.errors import ReleaseError
from ms.release.infra.github.workflows import (
    dispatch_app_candidate_workflow,
    dispatch_app_release_workflow,
    watch_run,
)

from .app_prepare import PreparedAppRelease


class ExternalNotesSnapshotLike(Protocol):
    @property
    def source_path(self) -> Path: ...

    @property
    def markdown(self) -> str: ...

    @property
    def sha256(self) -> str: ...


def publish_app_release(
    *,
    workspace_root: Path,
    console: ConsoleProtocol,
    tag: str,
    source_sha: str,
    notes_markdown: str | None,
    notes_source_path: str | None,
    watch: bool,
    dry_run: bool,
) -> Result[tuple[str, str], ReleaseError]:
    if notes_markdown is not None:
        source_label = notes_source_path or "(unknown source)"
        console.print(
            "release notes: external markdown attached from "
            f"{source_label} (prepended above auto-notes)",
            Style.DIM,
        )
    else:
        console.print("release notes: automatic notes only", Style.DIM)

    candidate = dispatch_app_candidate_workflow(
        workspace_root=workspace_root,
        source_sha=source_sha,
        console=console,
        dry_run=dry_run,
    )
    if isinstance(candidate, Err):
        return candidate

    if watch:
        watched = watch_run(
            workspace_root=workspace_root,
            run_id=candidate.value.id,
            repo_slug=config.APP_REPO_SLUG,
            console=console,
            dry_run=dry_run,
        )
        if isinstance(watched, Err):
            return watched

    release = dispatch_app_release_workflow(
        workspace_root=workspace_root,
        tag=tag,
        source_sha=source_sha,
        notes_markdown=notes_markdown,
        notes_source_path=notes_source_path,
        console=console,
        dry_run=dry_run,
    )
    if isinstance(release, Err):
        return release

    if watch:
        watched = watch_run(
            workspace_root=workspace_root,
            run_id=release.value.id,
            repo_slug=config.APP_REPO_SLUG,
            console=console,
            dry_run=dry_run,
        )
        if isinstance(watched, Err):
            return watched

    return Ok((candidate.value.url, release.value.url))


def resolve_app_publish_notes[SnapshotT: ExternalNotesSnapshotLike](
    *,
    notes_file: Path | None,
    load_external_notes_file_fn: Callable[..., Result[SnapshotT, ReleaseError]],
) -> Result[AppPublishNotes, ReleaseError]:
    if notes_file is None:
        return Ok(AppPublishNotes(markdown=None, source_path=None, sha256=None))

    notes = load_external_notes_file_fn(path=notes_file)
    if isinstance(notes, Err):
        return notes

    return Ok(
        AppPublishNotes(
            markdown=notes.value.markdown,
            source_path=str(notes.value.source_path.resolve()),
            sha256=notes.value.sha256,
        )
    )


def publish_app_release_workflows(
    *,
    publish_app_release_fn: Callable[..., Result[tuple[str, str], ReleaseError]],
    workspace_root: Path,
    console: ConsoleProtocol,
    prepared: PreparedAppRelease,
    notes: AppPublishNotes,
    watch: bool,
    dry_run: bool,
) -> Result[tuple[str, str], ReleaseError]:
    return publish_app_release_fn(
        workspace_root=workspace_root,
        console=console,
        tag=prepared.plan.tag,
        source_sha=prepared.source_sha,
        notes_markdown=notes.markdown,
        notes_source_path=notes.source_path,
        watch=watch,
        dry_run=dry_run,
    )
