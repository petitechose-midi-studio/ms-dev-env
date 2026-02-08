from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class OcSdkPin:
    repo: str
    sha: str


@dataclass(frozen=True, slots=True)
class OcSdkLock:
    version: str
    pins: tuple[OcSdkPin, ...]

    def pins_by_repo(self) -> dict[str, str]:
        return {p.repo: p.sha for p in self.pins}


@dataclass(frozen=True, slots=True)
class OcSdkLoad:
    lock: OcSdkLock | None
    source: str | None  # "git" | "gh"
    error: str | None


@dataclass(frozen=True, slots=True)
class OpenControlRepoState:
    repo: str
    path: Path
    exists: bool
    head_sha: str | None
    dirty: bool


@dataclass(frozen=True, slots=True)
class OcSdkMismatch:
    repo: str
    pinned_sha: str
    local_sha: str


@dataclass(frozen=True, slots=True)
class OpenControlPreflightReport:
    oc_sdk: OcSdkLoad
    repos: tuple[OpenControlRepoState, ...]
    mismatches: tuple[OcSdkMismatch, ...]

    def dirty_repos(self) -> tuple[OpenControlRepoState, ...]:
        return tuple(r for r in self.repos if r.exists and r.dirty)
