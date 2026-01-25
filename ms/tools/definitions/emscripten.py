"""Emscripten SDK tool definition.

Emscripten is a complete compiler toolchain to WebAssembly.
It's used for building the WebAssembly version of the project.

Website: https://emscripten.org/
GitHub: https://github.com/emscripten-core/emsdk

Note: Emscripten uses a special installation flow:
1. Git clone the emsdk repository
2. Run emsdk install latest
3. Run emsdk activate latest

This is handled by a custom install() method, not download+extract.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from ms.core.result import Result
from ms.tools.base import Mode, Tool, ToolSpec
from ms.tools.http import HttpError

if TYPE_CHECKING:
    from ms.platform.detection import Arch, Platform
    from ms.tools.http import HttpClient

__all__ = ["EmscriptenTool"]


class EmscriptenTool(Tool):
    """Emscripten SDK - custom git-based installation.

    Emscripten is special because:
    - Installed via git clone + emsdk script
    - Has its own version management (emsdk install/activate)
    - Provides emcc, emcmake, etc. in upstream/emscripten/
    - Requires EMSDK environment variable

    The actual installation is handled by the installer module,
    not by the standard download+extract flow.
    """

    spec = ToolSpec(
        id="emscripten",
        name="Emscripten SDK",
        required_for=frozenset({Mode.DEV}),
    )

    # Git repository URL
    repo_url: str = "https://github.com/emscripten-core/emsdk.git"
    repo: str = "emscripten-core/emsdk"

    def latest_version(self, http: HttpClient) -> Result[str, HttpError]:
        """Return a sentinel version for emsdk.

        The emsdk repo does not reliably expose GitHub "releases/latest".
        Our installation flow uses `emsdk install latest` regardless.
        """
        from ms.core.result import Ok

        return Ok("latest")

    def download_url(self, version: str, platform: Platform, arch: Arch) -> str:
        """Emscripten doesn't use standard downloads.

        Returns the git clone URL instead.
        """
        return self.repo_url

    def install_dir_name(self) -> str:
        """Emscripten installs to 'emsdk' directory."""
        return "emsdk"

    def bin_path(self, tools_dir: Path, platform: Platform) -> Path | None:
        """Get path to emcc compiler.

        The emcc binary is in emsdk/upstream/emscripten/.
        """
        emcc = "emcc.bat" if str(platform).lower() == "windows" else "emcc"
        return tools_dir / "emsdk" / "upstream" / "emscripten" / emcc

    def emcmake_path(self, tools_dir: Path, platform: Platform) -> Path:
        """Get path to emcmake wrapper."""
        name = "emcmake.bat" if str(platform).lower() == "windows" else "emcmake"
        return tools_dir / "emsdk" / "upstream" / "emscripten" / name

    def emsdk_path(self, tools_dir: Path, platform: Platform) -> Path:
        """Get path to emsdk script."""
        name = "emsdk.bat" if str(platform).lower() == "windows" else "emsdk"
        return tools_dir / "emsdk" / name

    def emsdk_env_path(self, tools_dir: Path, platform: Platform) -> Path:
        """Get path to emsdk_env script for environment setup."""
        if str(platform).lower() == "windows":
            return tools_dir / "emsdk" / "emsdk_env.bat"
        return tools_dir / "emsdk" / "emsdk_env.sh"

    def is_installed(self, tools_dir: Path, platform: Platform) -> bool:
        """Check if Emscripten is installed and activated.

        Checks for:
        1. emsdk repository exists
        2. upstream/emscripten/emcc exists (activated)
        """
        emsdk_dir = tools_dir / "emsdk"
        if not emsdk_dir.exists():
            return False

        # Check if activated (emcc exists)
        emcc = self.bin_path(tools_dir, platform)
        return emcc is not None and emcc.exists()

    def is_cloned(self, tools_dir: Path) -> bool:
        """Check if emsdk repository is cloned (but maybe not activated)."""
        emsdk_dir = tools_dir / "emsdk"
        return (emsdk_dir / ".git").exists()

    def emsdk_home(self, tools_dir: Path) -> Path:
        """Get EMSDK environment variable path."""
        return tools_dir / "emsdk"

    def uses_git_install(self) -> bool:
        """Indicate this tool uses git clone installation."""
        return True

    def get_install_commands(self, tools_dir: Path, platform: Platform) -> list[list[str]]:
        """Get commands to install Emscripten.

        Returns a list of command lists to execute in order:
        1. git clone (if not cloned)
        2. emsdk install latest
        3. emsdk activate latest

        This is used by the installer module.
        """
        emsdk_dir = tools_dir / "emsdk"
        emsdk = str(self.emsdk_path(tools_dir, platform))

        commands: list[list[str]] = []

        # Clone if needed
        if not self.is_cloned(tools_dir):
            commands.append(["git", "clone", self.repo_url, str(emsdk_dir)])

        # Install and activate
        commands.append([emsdk, "install", "latest"])
        commands.append([emsdk, "activate", "latest"])

        return commands

    def post_install(self, install_dir: Path, platform: Platform) -> None:
        """No post-install needed - emsdk handles everything."""
        pass
