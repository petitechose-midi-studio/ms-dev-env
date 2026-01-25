"""Tool resolution - finding installed tool binaries.

This module provides a ToolResolver that:
- Finds bundled tools in the tools directory
- Falls back to system PATH
- Returns the resolved binary path
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from ms.core.result import Err, Ok, Result

if TYPE_CHECKING:
    from ms.platform.detection import Platform
    from ms.tools.base import Tool

__all__ = ["ToolResolver", "ResolvedTool", "ToolNotFoundError"]


@dataclass(frozen=True, slots=True)
class ToolNotFoundError:
    """Error when tool cannot be found.

    Attributes:
        tool_id: ID of the tool that wasn't found
        message: Human-readable error message
    """

    tool_id: str
    message: str

    def __str__(self) -> str:
        return f"{self.message}: {self.tool_id}"


@dataclass(frozen=True, slots=True)
class ResolvedTool:
    """Information about a resolved tool.

    Attributes:
        tool_id: ID of the tool
        path: Path to the binary
        bundled: True if from tools directory, False if from system PATH
    """

    tool_id: str
    path: Path
    bundled: bool


class ToolResolver:
    """Resolves tool binaries.

    Searches for tools in order:
    1. Bundled tools in tools_dir
    2. System PATH

    Usage:
        resolver = ToolResolver(tools_dir, platform)
        result = resolver.resolve(ninja_tool)
        if is_ok(result):
            print(f"Found: {result.value.path}")
    """

    def __init__(self, tools_dir: Path, platform: Platform) -> None:
        """Initialize resolver.

        Args:
            tools_dir: Directory containing bundled tools
            platform: Current platform for binary naming
        """
        self._tools_dir = tools_dir
        self._platform = platform

    @property
    def tools_dir(self) -> Path:
        """Get tools directory."""
        return self._tools_dir

    @property
    def platform(self) -> Platform:
        """Get platform."""
        return self._platform

    def resolve(self, tool: Tool) -> Result[ResolvedTool, ToolNotFoundError]:
        """Resolve tool to binary path.

        Searches bundled tools first, then system PATH.

        Args:
            tool: Tool to resolve

        Returns:
            Ok with ResolvedTool, or Err with ToolNotFoundError
        """
        # Try bundled first
        bundled_path = tool.bin_path(self._tools_dir, self._platform)
        if bundled_path is not None and bundled_path.exists():
            return Ok(
                ResolvedTool(
                    tool_id=tool.spec.id,
                    path=bundled_path,
                    bundled=True,
                )
            )

        # Try system PATH
        system_path = self._find_in_path(tool.spec.id)
        if system_path is not None:
            return Ok(
                ResolvedTool(
                    tool_id=tool.spec.id,
                    path=system_path,
                    bundled=False,
                )
            )

        return Err(
            ToolNotFoundError(
                tool_id=tool.spec.id,
                message="Tool not found in bundled tools or system PATH",
            )
        )

    def _find_in_path(self, name: str) -> Path | None:
        """Find executable in system PATH.

        Args:
            name: Executable name

        Returns:
            Path to executable, or None if not found
        """
        # Use shutil.which for cross-platform PATH searching
        result = shutil.which(name)
        return Path(result) if result else None
