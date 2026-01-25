"""Base class for tools distributed via GitHub Releases.

Most tools (ninja, cmake, bun, SDL2, etc.) follow a similar pattern:
- Releases are on GitHub
- Assets are named with platform/arch suffixes
- Download URL follows: github.com/{repo}/releases/download/{tag}/{asset}

This module provides a base class that handles the common logic.
"""

from __future__ import annotations

from abc import abstractmethod
from pathlib import Path
from typing import TYPE_CHECKING

from ms.core.result import Result
from ms.tools.api import github_latest_release
from ms.tools.base import Tool, ToolSpec
from ms.tools.http import HttpError

if TYPE_CHECKING:
    from ms.platform.detection import Arch, Platform
    from ms.tools.http import HttpClient

__all__ = ["GitHubTool"]


class GitHubTool(Tool):
    """Base class for tools distributed via GitHub Releases.

    Subclasses must define:
    - spec: ToolSpec with tool metadata
    - repo: GitHub repository (e.g., "ninja-build/ninja")
    - asset_name(): Return asset filename for platform/arch

    Example:
        class NinjaTool(GitHubTool):
            spec = ToolSpec(id="ninja", name="Ninja", required_for=frozenset({Mode.DEV}))
            repo = "ninja-build/ninja"

            def asset_name(self, version: str, platform: Platform, arch: Arch) -> str:
                match platform:
                    case Platform.LINUX:
                        return f"ninja-linux.zip"
                    case Platform.MACOS:
                        return "ninja-mac.zip"
                    case Platform.WINDOWS:
                        return "ninja-win.zip"
    """

    spec: ToolSpec
    repo: str

    def latest_version(self, http: HttpClient) -> Result[str, HttpError]:
        """Fetch latest release version from GitHub.

        Args:
            http: HTTP client for API calls

        Returns:
            Ok with version string (without 'v' prefix), or Err with HttpError
        """
        return github_latest_release(http, self.repo)

    def download_url(self, version: str, platform: Platform, arch: Arch) -> str:
        """Get download URL for specific version and platform.

        Args:
            version: Tool version (without 'v' prefix)
            platform: Target platform
            arch: Target architecture

        Returns:
            Full URL to download the asset
        """
        asset = self.asset_name(version, platform, arch)
        return f"https://github.com/{self.repo}/releases/download/v{version}/{asset}"

    @abstractmethod
    def asset_name(self, version: str, platform: Platform, arch: Arch) -> str:
        """Get asset filename for platform/arch.

        Args:
            version: Tool version (may be needed for some tools)
            platform: Target platform
            arch: Target architecture

        Returns:
            Asset filename (e.g., "ninja-linux.zip")
        """
        ...

    def post_install(self, install_dir: Path, platform: Platform) -> None:
        """Make binary executable on Unix.

        Args:
            install_dir: Directory where tool was extracted
            platform: Target platform
        """
        if platform.is_unix:
            bin_path = install_dir / platform.exe_name(self.spec.id)
            if bin_path.exists():
                bin_path.chmod(0o755)
