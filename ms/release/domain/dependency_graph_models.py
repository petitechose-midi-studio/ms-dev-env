from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

ReleaseGraphRole = Literal[
    "bom_dependency",
    "bom_consumer",
    "dev_dependency",
    "release_producer",
    "release_consumer",
]


@dataclass(frozen=True, slots=True)
class ReleaseGraphNode:
    id: str
    repo: str
    local_path: str
    role: ReleaseGraphRole
    depends_on: tuple[str, ...] = ()
    validations: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ReleaseGraph:
    nodes: tuple[ReleaseGraphNode, ...]

    def by_id(self) -> dict[str, ReleaseGraphNode]:
        return {node.id: node for node in self.nodes}

    def by_repo(self) -> dict[str, ReleaseGraphNode]:
        return {node.repo: node for node in self.nodes}


__all__ = ["ReleaseGraph", "ReleaseGraphNode", "ReleaseGraphRole"]

