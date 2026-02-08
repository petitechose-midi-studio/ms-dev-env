"""Tool registry - facade for accessing and managing tools.

This module provides the ToolRegistry class which is the main entry point
for tool management operations:
- Listing available tools
- Filtering by mode (dev/enduser)
- Checking installation status
- Getting tool paths and environment variables

Usage:
    from ms.tools.registry import ToolRegistry
    from ms.platform.detection import detect_platform

    platform, arch = detect_platform()
    registry = ToolRegistry(tools_dir=Path("tools"), platform=platform, arch=arch)

    # List all tools
    for tool in registry.all_tools():
        print(f"{tool.spec.id}: {tool.spec.name}")

    # Check what's installed
    status = registry.get_status()
    for tool_id, installed in status.items():
        print(f"{tool_id}: {'installed' if installed else 'missing'}")
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from ms.tools.base import Mode, Tool
from ms.tools.definitions import ALL_TOOLS, get_tool, get_tools_by_mode

if TYPE_CHECKING:
    from ms.platform.detection import Arch, Platform

__all__ = ["ToolRegistry", "ToolStatus"]


@dataclass(frozen=True, slots=True)
class ToolStatus:
    """Status of a single tool.

    Attributes:
        tool: The tool instance
        installed: Whether the tool is installed
        version: Installed version (if tracked), None otherwise
        path: Path to the binary, None if not installed or system tool
    """

    tool: Tool
    installed: bool
    version: str | None = None
    path: Path | None = None


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
        arch: Arch,
    ) -> None:
        """Initialize the registry.

        Args:
            tools_dir: Directory where bundled tools are installed
            platform: Current platform
            arch: Current architecture
        """
        self._tools_dir = tools_dir
        self._platform = platform
        self._arch = arch

    @property
    def tools_dir(self) -> Path:
        """Get the tools directory."""
        return self._tools_dir

    @property
    def platform(self) -> Platform:
        """Get the current platform."""
        return self._platform

    @property
    def arch(self) -> Arch:
        """Get the current architecture."""
        return self._arch

    def all_tools(self) -> tuple[Tool, ...]:
        """Get all registered tools.

        Returns:
            Tuple of all tool instances
        """
        return ALL_TOOLS

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

    def get_status(self, tool: Tool | str) -> ToolStatus:
        """Get detailed status for a tool.

        Args:
            tool: Tool instance or tool ID

        Returns:
            ToolStatus with installation details

        Raises:
            ValueError: If tool ID is not found
        """
        if isinstance(tool, str):
            resolved = get_tool(tool)
            if resolved is None:
                raise ValueError(f"Unknown tool: {tool}")
            tool = resolved

        installed = tool.is_installed(self._tools_dir, self._platform)
        path = tool.bin_path(self._tools_dir, self._platform) if installed else None

        # Try to get version from state
        version: str | None = None
        if installed:
            from ms.tools.state import get_installed_version

            version = get_installed_version(self._tools_dir, tool.spec.id)

        return ToolStatus(
            tool=tool,
            installed=installed,
            version=version,
            path=path,
        )

    def get_all_status(self) -> dict[str, ToolStatus]:
        """Get status for all tools.

        Returns:
            Dict mapping tool ID to ToolStatus
        """
        return {tool.spec.id: self.get_status(tool) for tool in ALL_TOOLS}

    def get_missing_tools(self, mode: Mode | str = Mode.DEV) -> list[Tool]:
        """Get tools that are required but not installed.

        Args:
            mode: Mode to check requirements for

        Returns:
            List of missing tools
        """
        required = self.tools_for_mode(mode)
        return [tool for tool in required if not self.is_installed(tool)]

    def get_installed_tools(self) -> list[Tool]:
        """Get all installed tools.

        Returns:
            List of installed tools
        """
        return [tool for tool in ALL_TOOLS if self.is_installed(tool)]

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
            return emscripten.emcmake_path(self._tools_dir, self._platform)
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
