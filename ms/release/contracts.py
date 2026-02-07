"""Cross-layer contracts for the release bounded context."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

ReleaseMode = Literal["content", "app"]
ReleasePhase = Literal["plan", "prepare", "publish", "remove", "guided"]


@dataclass(frozen=True, slots=True)
class ReleaseRequest:
    """Normalized release request shared between CLI and flows."""

    workspace_root: Path
    mode: ReleaseMode
    phase: ReleasePhase
    dry_run: bool = False
    from_guided: bool = False


@dataclass(frozen=True, slots=True)
class ReleaseResult:
    """Flow outcome rendered by view adapters."""

    success: bool
    summary: str
    hint: str | None = None
    details: tuple[str, ...] = ()
