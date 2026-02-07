from __future__ import annotations

from pathlib import Path

from ms.core.result import Result
from ms.platform.files import atomic_write_text
from ms.release.domain.models import PinnedRepo, ReleaseChannel
from ms.release.errors import ReleaseError
from ms.release.infra.artifacts import notes_writer as _notes_writer
from ms.release.infra.artifacts.notes_writer import (
    ExternalNotesSnapshot,
    WrittenNotes,
    load_external_notes_file,
    notes_path_for_tag,
)


def write_release_notes(
    *,
    dist_repo_root: Path,
    channel: ReleaseChannel,
    tag: str,
    pinned: tuple[PinnedRepo, ...],
    user_notes: str | None,
    user_notes_file: Path | None,
) -> Result[WrittenNotes, ReleaseError]:
    original_write = _notes_writer.atomic_write_text
    _notes_writer.atomic_write_text = atomic_write_text
    try:
        return _notes_writer.write_release_notes(
            dist_repo_root=dist_repo_root,
            channel=channel,
            tag=tag,
            pinned=pinned,
            user_notes=user_notes,
            user_notes_file=user_notes_file,
        )
    finally:
        _notes_writer.atomic_write_text = original_write


__all__ = [
    "ExternalNotesSnapshot",
    "WrittenNotes",
    "load_external_notes_file",
    "notes_path_for_tag",
    "write_release_notes",
]
