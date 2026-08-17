from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

SelectionAction = Literal["select", "back", "cancel"]


@dataclass(frozen=True, slots=True)
class Selection[T]:
    action: SelectionAction
    value: T | None
    index: int
