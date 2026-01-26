"""SDL2 library tool definition.

SDL2 is a cross-platform development library for multimedia.
It's used for audio output in the native build.

Website: https://www.libsdl.org/
GitHub: https://github.com/libsdl-org/SDL

Note: SDL2 is only auto-installed on Windows (using the MinGW package).
On Linux/macOS, it should be installed via the system package manager.
"""

from __future__ import annotations

import shutil
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

    Uses the MinGW package which has:
    - Headers in include/SDL2/SDL.h (matches #include <SDL2/SDL.h>)
    - GNU-compatible libraries (works with Zig -target x86_64-windows-gnu)
    - Simpler than MSVC package (no manifest issues, no symlinks needed)
    """

    spec = ToolSpec(
        id="sdl2",
        name="SDL2",
        required_for=frozenset({Mode.DEV}),
        version_args=(),  # No version check - it's a library
    )

    repo = "libsdl-org/SDL"

    install_hints: dict[str, str] = {
        "linux": "sudo apt install libsdl2-dev",
        "macos": "brew install sdl2",
    }

    def latest_version(self, http: HttpClient) -> Result[str, HttpError]:
        """Fetch latest version."""
        return super().latest_version(http)

    def download_url(self, version: str, platform: Platform, arch: Arch) -> str:
        """Get download URL for Windows MinGW SDL2."""
        return f"https://github.com/{self.repo}/releases/download/release-{version}/SDL2-devel-{version}-mingw.zip"

    def asset_name(self, version: str, platform: Platform, arch: Arch) -> str:
        """Get asset name for SDL2 download."""
        return f"SDL2-devel-{version}-mingw.zip"

    def strip_components(self) -> int:
        """SDL2 MinGW archive: SDL2-X.X.X/ contains x86_64-w64-mingw32/."""
        return 1

    def bin_path(self, tools_dir: Path, platform: Platform) -> Path | None:
        """SDL2 DLL path."""
        if str(platform).lower() == "windows":
            return tools_dir / "sdl2" / "bin" / "SDL2.dll"
        return None

    def include_path(self, tools_dir: Path) -> Path:
        """Get the include path for SDL2 headers."""
        # MinGW package: include/SDL2/SDL.h
        return tools_dir / "sdl2" / "include"

    def lib_path(self, tools_dir: Path) -> Path:
        """Get the library path for SDL2."""
        return tools_dir / "sdl2" / "lib"

    def is_installed(self, tools_dir: Path, platform: Platform) -> bool:
        """Check if SDL2 is installed."""
        platform_str = str(platform).lower()

        if platform_str == "windows":
            # MinGW package: lib/libSDL2.a or lib/libSDL2.dll.a
            lib_path = tools_dir / "sdl2" / "lib" / "libSDL2.dll.a"
            return lib_path.exists()
        else:
            return shutil.which("sdl2-config") is not None

    def is_windows_only(self) -> bool:
        """SDL2 auto-install is Windows-only."""
        return True

    def get_install_hint(self, platform: Platform) -> str | None:
        """Get installation hint for non-Windows platforms."""
        return self.install_hints.get(str(platform).lower())

    def post_install(self, install_dir: Path, platform: Platform) -> None:
        """Move x86_64-w64-mingw32/ contents to root.

        MinGW package extracts to:
          sdl2/x86_64-w64-mingw32/{bin,include,lib,share}/
          sdl2/i686-w64-mingw32/...

        We want:
          sdl2/{bin,include,lib,share}/
        """
        if str(platform).lower() != "windows":
            return

        mingw64_dir = install_dir / "x86_64-w64-mingw32"
        if not mingw64_dir.exists():
            return

        # Move contents of x86_64-w64-mingw32/ to parent
        for item in mingw64_dir.iterdir():
            dest = install_dir / item.name
            if dest.exists():
                if dest.is_dir():
                    shutil.rmtree(dest)
                else:
                    dest.unlink()
            shutil.move(str(item), str(dest))

        # Remove empty mingw directories
        mingw64_dir.rmdir()
        mingw32_dir = install_dir / "i686-w64-mingw32"
        if mingw32_dir.exists():
            shutil.rmtree(mingw32_dir)
