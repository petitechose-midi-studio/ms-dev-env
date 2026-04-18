from __future__ import annotations

from pathlib import Path

from ms.core.result import Err, Ok, Result
from ms.output.console import ConsoleProtocol, Style
from ms.release.domain import config
from ms.release.domain.notes import AppPublishNotes
from ms.release.errors import ReleaseError
from ms.release.infra.artifacts.notes_writer import load_external_notes_file
from ms.release.infra.github.run_watch import watch_run
from ms.release.infra.github.workflows import dispatch_app_release_workflow

from .app_candidate_ensure import AppPublishResult, ensure_app_candidate


def publish_app_release(
    *,
    workspace_root: Path,
    console: ConsoleProtocol,
    tag: str,
    source_sha: str,
    tooling_sha: str,
    notes_markdown: str | None,
    notes_source_path: str | None,
    watch: bool,
    dry_run: bool,
) -> Result[AppPublishResult, ReleaseError]:
    if notes_markdown is not None:
        source_label = notes_source_path or "(unknown source)"
        console.print(
            "release notes: external markdown attached from "
            f"{source_label} (prepended above auto-notes)",
            Style.DIM,
        )
    else:
        console.print("release notes: automatic notes only", Style.DIM)

    candidate = ensure_app_candidate(
        workspace_root=workspace_root,
        source_sha=source_sha,
        tooling_sha=tooling_sha,
        console=console,
        dry_run=dry_run,
    )
    if isinstance(candidate, Err):
        return candidate

    if watch and candidate.value.run is not None:
        watched = watch_run(
            workspace_root=workspace_root,
            run_id=candidate.value.run.id,
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
        tooling_sha=tooling_sha,
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

    return Ok(AppPublishResult(candidate=candidate.value, release=release.value))
def resolve_app_publish_notes(
    *,
    notes_file: Path | None,
) -> Result[AppPublishNotes, ReleaseError]:
    if notes_file is None:
        return Ok(AppPublishNotes(markdown=None, source_path=None, sha256=None))

    notes = load_external_notes_file(path=notes_file)
    if isinstance(notes, Err):
        return notes

    return Ok(
        AppPublishNotes(
            markdown=notes.value.markdown,
            source_path=str(notes.value.source_path.resolve()),
            sha256=notes.value.sha256,
        )
    )
