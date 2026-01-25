"""CMake build system tool definition.

CMake is a cross-platform build system generator. It's used to configure
and generate build files for native and WASM builds.

GitHub: https://github.com/Kitware/CMake
"""

from __future__ import annotations

import shutil
from typing import TYPE_CHECKING

from ms.tools.base import Mode, ToolSpec
from ms.tools.github import GitHubTool

if TYPE_CHECKING:
    from pathlib import Path

    from ms.platform.detection import Arch, Platform

__all__ = ["CMakeTool"]


class CMakeTool(GitHubTool):
    """CMake build system generator.

    CMake archives have a root directory (cmake-{version}-{os}/) that needs
    to be stripped. On macOS, the archive contains a .app bundle that needs
    to be unpacked in post_install.
    """

    spec = ToolSpec(
        id="cmake",
        name="CMake",
        required_for=frozenset({Mode.DEV}),
    )
    repo = "Kitware/CMake"

    def asset_name(self, version: str, platform: Platform, arch: Arch) -> str:
        """Get asset filename for platform/arch.

        CMake release naming:
        - Linux x64: cmake-{version}-linux-x86_64.tar.gz
        - Linux ARM64: cmake-{version}-linux-aarch64.tar.gz
        - macOS: cmake-{version}-macos-universal.tar.gz
        - Windows: cmake-{version}-windows-x86_64.zip
        """
        from ms.platform.detection import Arch as A
        from ms.platform.detection import Platform as P

        match platform:
            case P.LINUX:
                arch_str = "aarch64" if arch == A.ARM64 else "x86_64"
                return f"cmake-{version}-linux-{arch_str}.tar.gz"
            case P.MACOS:
                return f"cmake-{version}-macos-universal.tar.gz"
            case P.WINDOWS:
                return f"cmake-{version}-windows-x86_64.zip"
            case _:
                return f"cmake-{version}-linux-x86_64.tar.gz"

    def strip_components(self) -> int:
        """CMake archives have a root directory to strip."""
        return 1

    def bin_path(self, tools_dir: Path, platform: Platform) -> Path | None:
        """CMake binary is in bin/ subdirectory."""
        return tools_dir / "cmake" / "bin" / platform.exe_name("cmake")

    def post_install(self, install_dir: Path, platform: Platform) -> None:
        """Handle macOS .app bundle extraction.

        On macOS, the archive extracts to a CMake.app bundle. We need to
        move the contents from CMake.app/Contents/* to the install directory.
        """
        from ms.platform.detection import Platform as P

        # macOS: extract from CMake.app bundle
        if platform == P.MACOS:
            app_bundle = install_dir / "CMake.app"
            if app_bundle.exists():
                contents_dir = app_bundle / "Contents"
                if contents_dir.exists():
                    # Move all items from Contents/ to install_dir/
                    for item in contents_dir.iterdir():
                        dest = install_dir / item.name
                        if dest.exists():
                            if dest.is_dir():
                                shutil.rmtree(dest)
                            else:
                                dest.unlink()
                        shutil.move(str(item), str(dest))
                    # Remove the now-empty .app bundle
                    shutil.rmtree(app_bundle)

        # Make binary executable on Unix
        if platform.is_unix:
            bin_path = self.bin_path(install_dir.parent, platform)
            if bin_path is not None and bin_path.exists():
                bin_path.chmod(0o755)
