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

from ms.platform.files import remove_tree
from ms.tools.base import Mode, ToolSpec
from ms.tools.github import GitHubTool

if TYPE_CHECKING:
    from ms.platform.detection import Arch, Platform

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
        if platform.is_windows:
            return tools_dir / "sdl2" / "bin" / "SDL2.dll"
        return None

    def lib_path(self, tools_dir: Path) -> Path:
        """Get the library path for SDL2."""
        return tools_dir / "sdl2" / "lib"

    def is_installed(self, tools_dir: Path, platform: Platform) -> bool:
        """Check if SDL2 is installed."""
        if platform.is_windows:
            # MinGW package: lib/libSDL2.a or lib/libSDL2.dll.a
            lib_path = tools_dir / "sdl2" / "lib" / "libSDL2.dll.a"
            return lib_path.exists()
        return shutil.which("sdl2-config") is not None

    def post_install(self, install_dir: Path, platform: Platform) -> None:
        """Move x86_64-w64-mingw32/ contents to root.

        MinGW package extracts to:
          sdl2/x86_64-w64-mingw32/{bin,include,lib,share}/
          sdl2/i686-w64-mingw32/...

        We want:
          sdl2/{bin,include,lib,share}/
        """
        if not platform.is_windows:
            return

        mingw64_dir = install_dir / "x86_64-w64-mingw32"
        if not mingw64_dir.exists():
            return

        # Move contents of x86_64-w64-mingw32/ to parent
        for item in mingw64_dir.iterdir():
            dest = install_dir / item.name
            if dest.exists():
                if dest.is_dir():
                    remove_tree(dest)
                else:
                    dest.unlink()
            shutil.move(str(item), str(dest))

        # Remove empty mingw directories
        mingw64_dir.rmdir()
        mingw32_dir = install_dir / "i686-w64-mingw32"
        if mingw32_dir.exists():
            remove_tree(mingw32_dir)
