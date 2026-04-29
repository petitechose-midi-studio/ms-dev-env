from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

DependencyReadinessStatus = Literal[
    "ok",
    "missing",
    "dirty",
    "no_upstream",
    "behind_remote",
    "ahead_unpushed",
    "diverged",
    "detached",
    "not_fetchable",
    "blocked_by_dependency",
    "repo_failed",
]


@dataclass(frozen=True, slots=True)
class DependencyReadinessItem:
    node_id: str
    repo: str
    path: Path
    status: DependencyReadinessStatus
    sha: str | None = None
    branch: str | None = None
    detail: str | None = None
    hint: str | None = None

    @property
    def is_blocking(self) -> bool:
        return self.status != "ok"


@dataclass(frozen=True, slots=True)
class DependencyReadinessReport:
    items: tuple[DependencyReadinessItem, ...]

    @property
    def is_ready(self) -> bool:
        return all(not item.is_blocking for item in self.items)

    def by_node_id(self) -> dict[str, DependencyReadinessItem]:
        return {item.node_id: item for item in self.items}


__all__ = [
    "DependencyReadinessItem",
    "DependencyReadinessReport",
    "DependencyReadinessStatus",
]
