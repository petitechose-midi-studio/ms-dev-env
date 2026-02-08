from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol

SelectionAction = Literal["select", "back", "cancel"]


class SelectionLike[T](Protocol):
    @property
    def action(self) -> SelectionAction: ...

    @property
    def value(self) -> T | None: ...

    @property
    def index(self) -> int: ...


@dataclass(frozen=True, slots=True)
class Selection[T]:
    action: SelectionAction
    value: T | None
    index: int
