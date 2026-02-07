from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from ms.core.result import Err, Ok, Result
from ms.output.console import ConsoleProtocol
from ms.release.errors import ReleaseError

from .app_prepare import PreparedAppRelease


class ExternalNotesSnapshotLike(Protocol):
    @property
    def source_path(self) -> Path: ...

    @property
    def markdown(self) -> str: ...

    @property
    def sha256(self) -> str: ...


@dataclass(frozen=True, slots=True)
class AppPublishNotes:
    markdown: str | None
    source_path: str | None
    sha256: str | None


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
