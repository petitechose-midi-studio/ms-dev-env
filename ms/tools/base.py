"""Base definitions for the tools system.

This module defines the core abstractions:
- Mode: Installation mode (dev vs end-user)
- ToolSpec: Immutable tool metadata
- Tool: Abstract base class for all tools
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum, auto
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ms.core.result import Result
    from ms.platform.detection import Arch, Platform
    from ms.tools.http import HttpClient, HttpError

__all__ = [
    "Mode",
    "ToolSpec",
    "Tool",
]


class Mode(Enum):
    """Installation mode.

    DEV: Development mode - all tools needed for building
    ENDUSER: End-user mode - minimal tools for running
    """

    DEV = auto()
    ENDUSER = auto()

    def __str__(self) -> str:
        return self.name.lower()


@dataclass(frozen=True, slots=True)
class ToolSpec:
    """Immutable tool metadata.

    Attributes:
        id: Unique identifier (e.g., "ninja", "cmake")
        name: Human-readable name (e.g., "Ninja", "CMake")
        required_for: Set of modes where this tool is required
        version_args: Arguments to get version (default: ("--version",))
    """

    id: str
    name: str
    required_for: frozenset[Mode]
    version_args: tuple[str, ...] = ("--version",)

    def __post_init__(self) -> None:
        """Validate tool spec."""
        if not self.id:
            raise ValueError("Tool id cannot be empty")
        if not self.name:
            raise ValueError("Tool name cannot be empty")
        if not self.id.isidentifier() or not self.id.islower():
            raise ValueError(f"Tool id must be lowercase identifier: {self.id!r}")

    def is_required_for(self, mode: Mode) -> bool:
        """Check if tool is required for given mode."""
        return mode in self.required_for


class Tool(ABC):
    """Abstract base class for all tools.

    Subclasses must define:
    - spec: ToolSpec with tool metadata
    - latest_version(): Fetch latest version from source
    - download_url(): Get download URL for version/platform

    Most methods have sensible defaults that can be overridden.
    """

    spec: ToolSpec

    @abstractmethod
    def latest_version(self, http: HttpClient) -> Result[str, HttpError]:
        """Fetch latest version from source.

        Args:
            http: HTTP client for API calls

        Returns:
            Ok with version string (without 'v' prefix), or Err
        """
        ...

    @abstractmethod
    def download_url(self, version: str, platform: Platform, arch: Arch) -> str:
        """Get download URL for specific version and platform.

        Args:
            version: Tool version (without 'v' prefix)
            platform: Target platform
            arch: Target architecture

        Returns:
            Full URL to download archive
        """
        ...

    def install_dir_name(self) -> str:
        """Get installation directory name.

        Default: use tool id from spec.

        Returns:
            Directory name under tools/ (e.g., "ninja", "cmake")
        """
        return self.spec.id

    def strip_components(self) -> int:
        """Get number of path components to strip when extracting.

        Default: 0 (no stripping).
        Override for tools with nested directories in archive.

        Returns:
            Number of leading path components to remove
        """
        return 0

    def bin_path(self, tools_dir: Path, platform: Platform) -> Path | None:
        """Get path to main binary.

        Default: tools_dir / {id} / {id}[.exe]

        Args:
            tools_dir: Base directory for bundled tools
            platform: Target platform

        Returns:
            Path to binary, or None if not applicable
        """
        return tools_dir / self.spec.id / platform.exe_name(self.spec.id)

    def is_installed(self, tools_dir: Path, platform: Platform) -> bool:
        """Check if tool is installed.

        Args:
            tools_dir: Base directory for bundled tools
            platform: Target platform

        Returns:
            True if binary exists
        """
        path = self.bin_path(tools_dir, platform)
        return path is not None and path.exists()

    def post_install(self, install_dir: Path, platform: Platform) -> None:
        """Perform post-installation actions.

        Default: no-op. Override for tools with special requirements.

        Args:
            install_dir: Directory where tool was extracted
            platform: Target platform
        """
        return None
