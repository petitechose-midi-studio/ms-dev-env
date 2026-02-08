from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class AppPublishNotes:
    markdown: str | None
    source_path: str | None
    sha256: str | None


@dataclass(frozen=True, slots=True)
class ExternalNotesSnapshot:
    source_path: Path
    markdown: str
    sha256: str
