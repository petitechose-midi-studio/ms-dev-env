"""PlatformIO tool definition.

PlatformIO is an open-source ecosystem for embedded development.

DEV policy in this workspace:
- PlatformIO is installed into a dedicated venv under tools/:
  tools/platformio/venv
- PlatformIO runtime directories are isolated to the workspace via env vars:
  PLATFORMIO_CORE_DIR, PLATFORMIO_CACHE_DIR, PLATFORMIO_BUILD_CACHE_DIR

This avoids touching ~/.platformio by default and improves reproducibility.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from ms.core.result import Err, Result
from ms.tools.base import Mode, Tool, ToolSpec
from ms.tools.http import HttpError

if TYPE_CHECKING:
    from ms.platform.detection import Arch, Platform
    from ms.tools.http import HttpClient

__all__ = ["PlatformioTool"]


class PlatformioTool(Tool):
    """PlatformIO - installed in tools/platformio/venv.

    Installation is performed by ToolchainService (venv + pip).
    """

    spec = ToolSpec(
        id="platformio",
        name="PlatformIO",
        required_for=frozenset({Mode.DEV}),
    )

    def latest_version(self, http: HttpClient) -> Result[str, HttpError]:
        """PlatformIO is installed via pip.

        Version is pinned in toolchains.toml.
        """
        return Err(
            HttpError(
                url="",
                status=0,
                message="PlatformIO version is pinned in toolchains.toml",
            )
        )

    def download_url(self, version: str, platform: Platform, arch: Arch) -> str:
        raise NotImplementedError("PlatformIO is installed via pip in a dedicated venv")

    def install_dir_name(self) -> str:
        return "platformio"

    def bin_path(self, tools_dir: Path, platform: Platform) -> Path | None:
        bin_dir = "Scripts" if str(platform).lower() == "windows" else "bin"
        exe = "pio.exe" if str(platform).lower() == "windows" else "pio"
        return tools_dir / "platformio" / "venv" / bin_dir / exe

    def is_installed(self, tools_dir: Path, platform: Platform) -> bool:
        pio = self.bin_path(tools_dir, platform)
        return pio is not None and pio.exists()

    def post_install(self, install_dir: Path, platform: Platform) -> None:
        """No post-install needed - script handles everything."""
        pass
