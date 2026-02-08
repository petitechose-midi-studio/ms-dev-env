from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class MenuOption[T]:
    value: T
    label: str
    detail: str | None = None
