"""Ninja build system tool definition.

Ninja is a small build system with a focus on speed. It's used as the
backend for CMake builds in this project.

GitHub: https://github.com/ninja-build/ninja
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ms.tools.base import Mode, ToolSpec
from ms.tools.github import GitHubTool

if TYPE_CHECKING:
    from ms.platform.detection import Arch, Platform

__all__ = ["NinjaTool"]


class NinjaTool(GitHubTool):
    """Ninja build system - simplest GitHub tool.

    Ninja releases are zip files with the binary directly inside
    (no nested directory), so strip_components = 0 (default).
    """

    spec = ToolSpec(
        id="ninja",
        name="Ninja",
        required_for=frozenset({Mode.DEV}),
    )
    repo = "ninja-build/ninja"

    def asset_name(self, version: str, platform: Platform, arch: Arch) -> str:
        """Get asset filename for platform/arch.

        Ninja release naming:
        - Linux x64: ninja-linux.zip
        - Linux ARM64: ninja-linux-aarch64.zip
        - macOS (universal): ninja-mac.zip
        - Windows: ninja-win.zip
        """
        from ms.platform.detection import Arch as A
        from ms.platform.detection import Platform as P

        match platform:
            case P.LINUX:
                suffix = "-aarch64" if arch == A.ARM64 else ""
                return f"ninja-linux{suffix}.zip"
            case P.MACOS:
                return "ninja-mac.zip"
            case P.WINDOWS:
                return "ninja-win.zip"
            case _:
                return "ninja-linux.zip"
