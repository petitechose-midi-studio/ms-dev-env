"""Tool definitions module.

This module exports all tool definitions and provides a registry
for looking up tools by ID.

Usage:
    from ms.tools.definitions import ALL_TOOLS, get_tool

    # Get all tools
    for tool in ALL_TOOLS:
        print(f"{tool.spec.id}: {tool.spec.name}")

    # Get specific tool by ID
    ninja = get_tool("ninja")
    if ninja:
        print(f"Ninja: {ninja.spec.name}")
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ms.tools.definitions.bun import BunTool
from ms.tools.definitions.cargo import CargoTool
from ms.tools.definitions.cmake import CMakeTool
from ms.tools.definitions.emscripten import EmscriptenTool
from ms.tools.definitions.jdk import JdkTool
from ms.tools.definitions.maven import MavenTool
from ms.tools.definitions.ninja import NinjaTool
from ms.tools.definitions.platformio import PlatformioTool
from ms.tools.definitions.sdl2 import Sdl2Tool
from ms.tools.definitions.uv import UvTool
from ms.tools.definitions.zig import ZigTool

if TYPE_CHECKING:
    from ms.tools.base import Tool

__all__ = [
    # Tool classes
    "BunTool",
    "CargoTool",
    "CMakeTool",
    "EmscriptenTool",
    "JdkTool",
    "MavenTool",
    "NinjaTool",
    "PlatformioTool",
    "Sdl2Tool",
    "UvTool",
    "ZigTool",
    # Registry
    "ALL_TOOLS",
    "get_tool",
]


# All tool instances
ALL_TOOLS: tuple[Tool, ...] = (
    NinjaTool(),
    CMakeTool(),
    BunTool(),
    UvTool(),
    JdkTool(),
    MavenTool(),
    EmscriptenTool(),
    PlatformioTool(),
    CargoTool(),
    Sdl2Tool(),
    ZigTool(),
)

# Tool lookup by ID
_TOOLS_BY_ID: dict[str, Tool] = {tool.spec.id: tool for tool in ALL_TOOLS}


def get_tool(tool_id: str) -> Tool | None:
    """Get a tool by its ID.

    Args:
        tool_id: Tool identifier (e.g., "ninja", "cmake")

    Returns:
        Tool instance if found, None otherwise

    Example:
        >>> ninja = get_tool("ninja")
        >>> if ninja:
        ...     print(ninja.spec.name)  # "Ninja"
    """
    return _TOOLS_BY_ID.get(tool_id)
