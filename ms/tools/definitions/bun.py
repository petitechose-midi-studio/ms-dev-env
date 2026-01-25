"""Bun runtime tool definition.

Bun is a fast JavaScript runtime, bundler, and package manager.
Used for building TypeScript/JavaScript components.

GitHub: https://github.com/oven-sh/bun
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from ms.core.result import Result
from ms.tools.api import github_latest_release
from ms.tools.base import Mode, Tool, ToolSpec
from ms.tools.http import HttpError

if TYPE_CHECKING:
    from ms.platform.detection import Arch, Platform
    from ms.tools.http import HttpClient

__all__ = ["BunTool"]


class BunTool(Tool):
    """Bun JavaScript runtime.

    Bun uses GitHub releases but with a different tag format (bun-v1.x.x).
    Archives have a root directory to strip.
    """

    spec = ToolSpec(
        id="bun",
        name="Bun",
        required_for=frozenset({Mode.DEV}),
    )
    repo = "oven-sh/bun"

    def latest_version(self, http: HttpClient) -> Result[str, HttpError]:
        """Fetch latest version from GitHub.

        Bun uses tags like "bun-v1.1.0", so we need to strip both "bun-" and "v" prefixes.
        github_latest_release only strips leading 'v', so "bun-v1.1.0" becomes "bun-v1.1.0".
        We then strip "bun-" and "v" to get "1.1.0".
        """
        from ms.core.result import Err, Ok

        result = github_latest_release(http, self.repo)
        if isinstance(result, Err):
            return result
        version = result.value.removeprefix("bun-").removeprefix("v")
        return Ok(version)

    def download_url(self, version: str, platform: Platform, arch: Arch) -> str:
        """Get download URL for specific version and platform.

        Bun asset naming:
        - Linux x64: bun-linux-x64.zip
        - Linux ARM64: bun-linux-aarch64.zip
        - macOS x64: bun-darwin-x64.zip
        - macOS ARM64: bun-darwin-aarch64.zip
        - Windows x64: bun-windows-x64.zip
        """
        from ms.platform.detection import Arch as A
        from ms.platform.detection import Platform as P

        match (platform, arch):
            case (P.LINUX, A.X64):
                asset = "bun-linux-x64.zip"
            case (P.LINUX, A.ARM64):
                asset = "bun-linux-aarch64.zip"
            case (P.MACOS, A.X64):
                asset = "bun-darwin-x64.zip"
            case (P.MACOS, A.ARM64):
                asset = "bun-darwin-aarch64.zip"
            case (P.WINDOWS, A.X64):
                asset = "bun-windows-x64.zip"
            case _:
                asset = "bun-linux-x64.zip"

        # Bun uses "bun-v{version}" tag format
        tag = f"bun-v{version}"
        return f"https://github.com/{self.repo}/releases/download/{tag}/{asset}"

    def strip_components(self) -> int:
        """Bun archives have a root directory to strip."""
        return 1

    def bin_path(self, tools_dir: Path, platform: Platform) -> Path | None:
        """Bun binary is directly in the bun/ directory."""
        return tools_dir / "bun" / platform.exe_name("bun")

    def post_install(self, install_dir: Path, platform: Platform) -> None:
        """Make binary executable on Unix."""
        if platform.is_unix:
            bin_path = install_dir / platform.exe_name(self.spec.id)
            if bin_path.exists():
                bin_path.chmod(0o755)
