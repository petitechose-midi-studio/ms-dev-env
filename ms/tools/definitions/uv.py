"""UV tool definition.

UV is the package manager used to run this workspace CLI via `uv run ...`.

DEV policy:
- UV is treated as a SYSTEM dependency (like git/gh).
- We do not attempt to self-install/upgrade UV from within `ms`, to avoid
  self-overwrite issues (especially on Windows).

Install: https://docs.astral.sh/uv/
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import TYPE_CHECKING

from ms.core.result import Err, Result
from ms.tools.base import Mode, Tool, ToolSpec
from ms.tools.http import HttpError

if TYPE_CHECKING:
    from ms.platform.detection import Arch, Platform
    from ms.tools.http import HttpClient

__all__ = ["UvTool"]


class UvTool(Tool):
    """UV (system tool)."""

    spec = ToolSpec(
        id="uv",
        name="UV",
        required_for=frozenset({Mode.DEV}),
    )

    install_hint: str = "Install uv: https://docs.astral.sh/uv/"

    def latest_version(self, http: HttpClient) -> Result[str, HttpError]:
        return Err(HttpError(url="", status=0, message=f"System tool - {self.install_hint}"))

    def download_url(self, version: str, platform: Platform, arch: Arch) -> str:
        raise NotImplementedError(f"UV is a system tool. {self.install_hint}")

    def bin_path(self, tools_dir: Path, platform: Platform) -> Path | None:
        return None

    def is_installed(self, tools_dir: Path, platform: Platform) -> bool:
        return shutil.which("uv") is not None

    def is_system_tool(self) -> bool:
        return True

    def system_path(self, platform: Platform) -> Path | None:
        found = shutil.which("uv")
        return Path(found) if found else None
