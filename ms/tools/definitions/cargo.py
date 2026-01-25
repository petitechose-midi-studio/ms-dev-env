"""Cargo (Rust) tool definition.

Cargo is the Rust package manager and build tool. It's used for
building the oc-bridge native MIDI bridge.

Website: https://www.rust-lang.org/
Install: https://rustup.rs/

Note: Cargo is a SYSTEM tool - it must be installed by the user via rustup.
This tool only verifies its presence in PATH, it doesn't download anything.
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

__all__ = ["CargoTool"]


class CargoTool(Tool):
    """Cargo (Rust) - system tool requiring manual installation.

    Cargo cannot be auto-installed because:
    - Rustup is the official installer and handles toolchains
    - Installation is interactive and platform-specific
    - Users typically want control over Rust toolchain versions

    This tool only checks if cargo is available in PATH.
    """

    spec = ToolSpec(
        id="cargo",
        name="Cargo (Rust)",
        required_for=frozenset({Mode.DEV}),
    )

    # Installation hint for users
    install_hint: str = "Install Rust via https://rustup.rs/"

    def latest_version(self, http: HttpClient) -> Result[str, HttpError]:
        """System tools don't have downloadable versions.

        Returns Err indicating this is a system tool.
        """
        return Err(
            HttpError(
                url="",
                status=0,
                message=f"System tool - install manually: {self.install_hint}",
            )
        )

    def download_url(self, version: str, platform: Platform, arch: Arch) -> str:
        """System tools cannot be downloaded.

        Raises NotImplementedError with install instructions.
        """
        raise NotImplementedError(f"Cargo is a system tool. {self.install_hint}")

    def bin_path(self, tools_dir: Path, platform: Platform) -> Path | None:
        """Cargo is found via system PATH, not in tools_dir.

        Returns None since cargo isn't in the bundled tools directory.
        """
        return None

    def is_installed(self, tools_dir: Path, platform: Platform) -> bool:
        """Check if cargo is available in system PATH.

        Note: This ignores tools_dir since cargo is a system tool.
        """
        return shutil.which("cargo") is not None

    def system_path(self, platform: Platform) -> Path | None:
        """Get path to cargo from system PATH.

        Returns:
            Path to cargo executable, or None if not found
        """
        result = shutil.which("cargo")
        return Path(result) if result else None

    def is_system_tool(self) -> bool:
        """Indicate this is a system tool."""
        return True
