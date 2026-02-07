from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

HardwareErrorKind = Literal["script_missing", "build_failed", "upload_failed", "no_platformio"]
HardwareAction = Literal["build", "upload"]


@dataclass(frozen=True, slots=True)
class HardwareError:
    """Error from hardware operations."""

    kind: HardwareErrorKind
    message: str
    hint: str | None = None


def failure_kind(action: HardwareAction) -> Literal["build_failed", "upload_failed"]:
    if action == "build":
        return "build_failed"
    return "upload_failed"
