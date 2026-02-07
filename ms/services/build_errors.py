from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class AppNotFound:
    name: str
    available: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class SdlAppNotFound:
    app_name: str


@dataclass(frozen=True, slots=True)
class AppConfigInvalid:
    path: Path
    reason: str


@dataclass(frozen=True, slots=True)
class ToolMissing:
    tool_id: str
    hint: str = "Run: uv run ms sync --tools"


@dataclass(frozen=True, slots=True)
class PrereqMissing:
    name: str
    hint: str


@dataclass(frozen=True, slots=True)
class ConfigureFailed:
    returncode: int


@dataclass(frozen=True, slots=True)
class CompileFailed:
    returncode: int


@dataclass(frozen=True, slots=True)
class OutputMissing:
    path: Path


BuildError = (
    AppNotFound
    | SdlAppNotFound
    | AppConfigInvalid
    | ToolMissing
    | PrereqMissing
    | ConfigureFailed
    | CompileFailed
    | OutputMissing
)
