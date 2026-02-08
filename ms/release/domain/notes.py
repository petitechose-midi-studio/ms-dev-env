from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class AppPublishNotes:
    markdown: str | None
    source_path: str | None
    sha256: str | None
