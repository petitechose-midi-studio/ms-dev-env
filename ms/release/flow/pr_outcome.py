from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

PrMergeKind = Literal["merged_pr", "already_merged"]


@dataclass(frozen=True, slots=True)
class PrMergeOutcome:
    kind: PrMergeKind
    url: str | None
    label: str

    def display(self) -> str:
        return self.url or self.label

    def __str__(self) -> str:
        return self.display()
