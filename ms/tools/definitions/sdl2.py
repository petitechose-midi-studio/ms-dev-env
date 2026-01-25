"""SDL2 library tool definition.

SDL2 is a cross-platform development library for multimedia.
It's used for audio output in the native build.

Website: https://www.libsdl.org/
GitHub: https://github.com/libsdl-org/SDL

Note: SDL2 is only auto-installed on Windows. On Linux/macOS, it should
be installed via the system package manager (apt, brew, etc.).
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from ms.core.result import Result
from ms.tools.base import Mode, ToolSpec
from ms.tools.github import GitHubTool
from ms.tools.http import HttpError

if TYPE_CHECKING:
    from ms.platform.detection import Arch, Platform
    from ms.tools.http import HttpClient

__all__ = ["Sdl2Tool"]


class Sdl2Tool(GitHubTool):
    """SDL2 library - Windows-only auto-install.

    SDL2 is special because:
    - It's a library (DLL), not an executable
    - Only auto-installed on Windows
    - On Linux/macOS, installed via system package manager
    - Archives have a nested structure to navigate

    On Windows, we download the prebuilt MinGW development library.
    """

    spec = ToolSpec(
        id="sdl2",
        name="SDL2",
        required_for=frozenset({Mode.DEV}),
        version_args=(),  # No version check - it's a library
    )

    repo = "libsdl-org/SDL"

    # Install hints for non-Windows platforms
    install_hints: dict[str, str] = {
        "linux": "sudo apt install libsdl2-dev",
        "macos": "brew install sdl2",
    }

    def latest_version(self, http: HttpClient) -> Result[str, HttpError]:
        """Fetch latest version - only meaningful on Windows."""
        return super().latest_version(http)

    def download_url(self, version: str, platform: Platform, arch: Arch) -> str:
        """Get download URL for Windows MinGW SDL2.

        Only Windows x64 is supported for auto-download.
        """
        # SDL2 uses "release-X.Y.Z" tags and "SDL2-devel-X.Y.Z-mingw.zip" assets
        return f"https://github.com/{self.repo}/releases/download/release-{version}/SDL2-devel-{version}-mingw.zip"

    def asset_name(self, version: str, platform: Platform, arch: Arch) -> str:
        """Get asset name for SDL2 download."""
        return f"SDL2-devel-{version}-mingw.zip"

    def strip_components(self) -> int:
        """SDL2 archive has a root directory to strip."""
        return 1

    def bin_path(self, tools_dir: Path, platform: Platform) -> Path | None:
        """SDL2 is a library, not an executable.

        Returns the DLL path on Windows, None on other platforms.
        """
        if str(platform).lower() == "windows":
            return tools_dir / "sdl2" / "x86_64-w64-mingw32" / "bin" / "SDL2.dll"
        return None

    def include_path(self, tools_dir: Path) -> Path:
        """Get the include path for SDL2 headers."""
        return tools_dir / "sdl2" / "x86_64-w64-mingw32" / "include" / "SDL2"

    def lib_path(self, tools_dir: Path) -> Path:
        """Get the library path for SDL2."""
        return tools_dir / "sdl2" / "x86_64-w64-mingw32" / "lib"

    def is_installed(self, tools_dir: Path, platform: Platform) -> bool:
        """Check if SDL2 is installed.

        On Windows: check if DLL exists in tools dir.
        On Linux/macOS: check if sdl2-config is in PATH (from system install).
        """
        platform_str = str(platform).lower()

        if platform_str == "windows":
            dll_path = self.bin_path(tools_dir, platform)
            return dll_path is not None and dll_path.exists()
        else:
            # On Unix, check for system install via sdl2-config
            import shutil

            return shutil.which("sdl2-config") is not None

    def is_windows_only(self) -> bool:
        """SDL2 auto-install is Windows-only."""
        return True

    def get_install_hint(self, platform: Platform) -> str | None:
        """Get installation hint for non-Windows platforms."""
        platform_str = str(platform).lower()
        return self.install_hints.get(platform_str)

    def post_install(self, install_dir: Path, platform: Platform) -> None:
        """No post-install needed for SDL2 library."""
        pass
