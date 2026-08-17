"""Tool registry - facade for accessing and managing tools.

This module provides the ToolRegistry class which is the main entry point
for tool management operations:
- Listing available tools
- Filtering by mode (dev/enduser)
- Checking installation status
- Getting tool paths and environment variables

The registry only exposes operations needed by build and toolchain services.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from ms.tools.base import Mode, Tool
from ms.tools.definitions import ALL_TOOLS, get_tool, get_tools_by_mode

if TYPE_CHECKING:
    from ms.platform.detection import Platform

__all__ = ["ToolRegistry"]


class ToolRegistry:
    """Registry for accessing and managing tools.

    This is the main facade for tool operations. It provides:
    - Tool listing and filtering
    - Installation status checking
    - Path resolution
    - Environment variable generation

    The registry is stateless - it queries the filesystem for status
    on each call rather than caching.
    """

    def __init__(
        self,
        tools_dir: Path,
        platform: Platform,
    ) -> None:
        """Initialize the registry.

        Args:
            tools_dir: Directory where bundled tools are installed
            platform: Current platform
        """
        self._tools_dir = tools_dir
        self._platform = platform

    @property
    def tools_dir(self) -> Path:
        """Get the tools directory."""
        return self._tools_dir

    def get_tool(self, tool_id: str) -> Tool | None:
        """Get a tool by ID.

        Args:
            tool_id: Tool identifier (e.g., "ninja", "cmake")

        Returns:
            Tool instance if found, None otherwise
        """
        return get_tool(tool_id)

    def tools_for_mode(self, mode: Mode | str) -> list[Tool]:
        """Get tools required for a specific mode.

        Args:
            mode: Mode enum or string ("dev" or "enduser")

        Returns:
            List of tools required for that mode
        """
        mode_str = ("dev" if mode == Mode.DEV else "enduser") if isinstance(mode, Mode) else mode
        return get_tools_by_mode(mode_str)

    def is_installed(self, tool: Tool | str) -> bool:
        """Check if a tool is installed.

        Args:
            tool: Tool instance or tool ID

        Returns:
            True if installed, False otherwise
        """
        if isinstance(tool, str):
            resolved = get_tool(tool)
            if resolved is None:
                return False
            tool = resolved
        return tool.is_installed(self._tools_dir, self._platform)

    def get_bin_path(self, tool: Tool | str) -> Path | None:
        """Get path to a tool's binary.

        Args:
            tool: Tool instance or tool ID

        Returns:
            Path to binary if installed, None otherwise
        """
        if isinstance(tool, str):
            resolved = get_tool(tool)
            if resolved is None:
                return None
            tool = resolved

        if not tool.is_installed(self._tools_dir, self._platform):
            return None

        return tool.bin_path(self._tools_dir, self._platform)

    def get_env_vars(self) -> dict[str, str]:
        """Get environment variables for all installed tools.

        Returns dict with variables like:
        - JAVA_HOME for JDK
        - EMSDK for Emscripten
        - M2_HOME for Maven

        Returns:
            Dict of environment variable name to value
        """
        env: dict[str, str] = {}

        # JDK - JAVA_HOME
        jdk = get_tool("jdk")
        if jdk and self.is_installed(jdk):
            from ms.tools.definitions.jdk import JdkTool

            if isinstance(jdk, JdkTool):
                env["JAVA_HOME"] = str(jdk.java_home(self._tools_dir))

        # Maven - M2_HOME
        maven = get_tool("maven")
        if maven and self.is_installed(maven):
            from ms.tools.definitions.maven import MavenTool

            if isinstance(maven, MavenTool):
                env["M2_HOME"] = str(maven.m2_home(self._tools_dir))

        # Emscripten - EMSDK
        emscripten = get_tool("emscripten")
        if emscripten and self.is_installed(emscripten):
            from ms.tools.definitions.emscripten import EmscriptenTool

            if isinstance(emscripten, EmscriptenTool):
                env["EMSDK"] = str(emscripten.emsdk_home(self._tools_dir))

        return env

    def get_path_additions(self) -> list[Path]:
        """Get directories to add to PATH for installed tools.

        Returns:
            List of directories containing tool binaries
        """
        paths: list[Path] = []

        for tool in ALL_TOOLS:
            if not self.is_installed(tool):
                continue

            bin_path = tool.bin_path(self._tools_dir, self._platform)
            if bin_path is not None:
                # Add the directory containing the binary
                bin_dir = bin_path.parent
                if bin_dir not in paths:
                    paths.append(bin_dir)

        return paths

    # -------------------------------------------------------------------------
    # Tool-specific path accessors
    # -------------------------------------------------------------------------

    def get_sdl2_dll(self) -> Path | None:
        """Get path to SDL2.dll (Windows only)."""
        sdl2 = get_tool("sdl2")
        if sdl2 is None or not self.is_installed(sdl2):
            return None
        return sdl2.bin_path(self._tools_dir, self._platform)

    def get_sdl2_lib(self) -> Path | None:
        """Get path to SDL2 import library (e.g., libSDL2.dll.a)."""
        sdl2 = get_tool("sdl2")
        if sdl2 is None or not self.is_installed(sdl2):
            return None
        from ms.tools.definitions.sdl2 import Sdl2Tool

        if isinstance(sdl2, Sdl2Tool):
            lib_dir = sdl2.lib_path(self._tools_dir)
            return lib_dir / "libSDL2.dll.a"
        return None

    def get_emcmake(self) -> Path | None:
        """Get path to emcmake (Emscripten cmake wrapper)."""
        emscripten = get_tool("emscripten")
        if emscripten is None or not self.is_installed(emscripten):
            return None
        from ms.tools.definitions.emscripten import EmscriptenTool

        if isinstance(emscripten, EmscriptenTool):
            return emscripten.emcmake_path(self._tools_dir)
        return None

    def get_em_config(self) -> Path | None:
        """Get path to Emscripten config file (.emscripten)."""
        emscripten = get_tool("emscripten")
        if emscripten is None or not self.is_installed(emscripten):
            return None
        from ms.tools.definitions.emscripten import EmscriptenTool

        if isinstance(emscripten, EmscriptenTool):
            return emscripten.emsdk_home(self._tools_dir) / ".emscripten"
        return None

    def get_zig_wrapper(self, name: str) -> Path | None:
        """Get path to a Zig wrapper script (e.g., zig-cc.cmd).

        Args:
            name: Wrapper name without extension (e.g., "zig-cc")

        Returns:
            Path to wrapper if Zig is installed, None otherwise
        """
        zig = get_tool("zig")
        if zig is None or not self.is_installed(zig):
            return None
        ext = ".cmd" if self._platform.is_windows else ""
        return self._tools_dir / "bin" / f"{name}{ext}"
