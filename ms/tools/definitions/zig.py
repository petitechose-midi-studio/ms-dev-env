"""Zig compiler toolchain definition.

Zig is a systems programming language with a bundled C/C++ compiler.
Used as the primary compiler for Windows native builds, producing
MSVC-compatible binaries without requiring Visual Studio.

Website: https://ziglang.org/
GitHub: https://github.com/ziglang/zig

Note: Zig is only auto-installed on Windows for native builds.
On Linux/macOS, the system compiler (GCC/Clang) is used instead.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from ms.tools.base import Mode, ToolSpec
from ms.tools.github import GitHubTool

if TYPE_CHECKING:
    from ms.platform.detection import Arch, Platform

__all__ = ["ZigTool"]


class ZigTool(GitHubTool):
    """Zig compiler - Windows-only for native builds.

    Zig provides a C/C++ compiler that can target GNU ABI,
    allowing us to produce Windows binaries that link with
    MinGW-compiled libraries (like SDL2 MinGW) without Visual Studio.

    Uses -target x86_64-windows-gnu to produce GNU-compatible binaries.
    """

    spec = ToolSpec(
        id="zig",
        name="Zig",
        required_for=frozenset({Mode.DEV}),
        version_args=("version",),
    )
    repo = "ziglang/zig"

    def download_url(self, version: str, platform: Platform, arch: Arch) -> str:
        """Download from ziglang.org (not GitHub releases).

        Zig publishes releases on their own CDN which is more reliable
        than GitHub releases for large binaries.
        """
        from ms.platform.detection import Arch as A
        from ms.platform.detection import Platform as P

        arch_str = "aarch64" if arch == A.ARM64 else "x86_64"
        plat_map = {P.WINDOWS: "windows", P.LINUX: "linux", P.MACOS: "macos"}
        ext = "zip" if platform == P.WINDOWS else "tar.xz"
        return f"https://ziglang.org/download/{version}/zig-{plat_map[platform]}-{arch_str}-{version}.{ext}"

    def asset_name(self, version: str, platform: Platform, arch: Arch) -> str:
        """Get asset filename for platform/arch."""
        from ms.platform.detection import Arch as A
        from ms.platform.detection import Platform as P

        arch_str = "aarch64" if arch == A.ARM64 else "x86_64"
        plat_map = {P.WINDOWS: "windows", P.LINUX: "linux", P.MACOS: "macos"}
        ext = "zip" if platform == P.WINDOWS else "tar.xz"
        return f"zig-{plat_map[platform]}-{arch_str}-{version}.{ext}"

    def strip_components(self) -> int:
        """Zig archives have a root directory to strip."""
        return 1

    def bin_path(self, tools_dir: Path, platform: Platform) -> Path | None:
        """Zig binary path."""
        return tools_dir / "zig" / platform.exe_name("zig")

    def is_windows_only(self) -> bool:
        """Zig auto-install is Windows-only (Linux/macOS use system compiler)."""
        return True
