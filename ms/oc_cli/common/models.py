from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


class OCPlatform:
    """Minimal platform helper."""

    def __init__(self) -> None:
        self.is_windows = os.name == "nt"


@dataclass(frozen=True, slots=True)
class OCContext:
    project_root: Path
    env_name: str
    pio: str
    platform: OCPlatform
