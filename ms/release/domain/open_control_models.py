from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

OPEN_CONTROL_BOM_REPOS: tuple[str, ...] = (
    "framework",
    "note",
    "hal-common",
    "hal-teensy",
    "ui-lvgl",
    "ui-lvgl-components",
)

OPEN_CONTROL_NATIVE_CI_REPOS: tuple[str, ...] = (
    "framework",
    "note",
)


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
class DerivedBomLock:
    source: str
    pins: tuple[OcSdkPin, ...]
    expected_repos: tuple[str, ...]

    def pins_by_repo(self) -> dict[str, str]:
        return {p.repo: p.sha for p in self.pins}


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
    derived_lock: DerivedBomLock | None = None
    comparison: BomStateComparison | None = None

    def dirty_repos(self) -> tuple[OpenControlRepoState, ...]:
        return tuple(r for r in self.repos if r.exists and r.dirty)


BomComparisonStatus = Literal["aligned", "promotion_required", "blocked"]


@dataclass(frozen=True, slots=True)
class BomRepoState:
    repo: str
    bom_sha: str | None
    workspace_sha: str | None
    derived_sha: str | None
    workspace_exists: bool
    workspace_dirty: bool


@dataclass(frozen=True, slots=True)
class BomStateComparison:
    repos: tuple[BomRepoState, ...]
    status: BomComparisonStatus
    blockers: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class BomPromotionItem:
    repo: str
    from_sha: str | None
    to_sha: str
    changed: bool


@dataclass(frozen=True, slots=True)
class BomPromotionPlan:
    source: Literal["workspace"]
    current_version: str
    next_version: str
    items: tuple[BomPromotionItem, ...]
    requires_write: bool
