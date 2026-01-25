# SPDX-License-Identifier: MIT
"""Common utilities for checkers.

This module provides shared functionality used by all checkers:
- CommandRunner protocol for subprocess abstraction
- Hints loading and lookup
- Common helper functions
"""

from __future__ import annotations

import subprocess
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol, cast


class CommandRunner(Protocol):
    """Protocol for running shell commands.

    This abstraction allows mocking subprocess calls in tests.
    """

    def run(
        self, args: list[str], *, capture: bool = True, cwd: Path | None = None
    ) -> subprocess.CompletedProcess[str]:
        """Run a command and return the result.

        Args:
            args: Command and arguments
            capture: Whether to capture stdout/stderr
            cwd: Working directory (optional)

        Returns:
            CompletedProcess with returncode, stdout, stderr
        """
        ...


class DefaultCommandRunner:
    """Default command runner using subprocess.run."""

    def run(
        self, args: list[str], *, capture: bool = True, cwd: Path | None = None
    ) -> subprocess.CompletedProcess[str]:
        """Run a command using subprocess."""
        return subprocess.run(
            args,
            capture_output=capture,
            text=True,
            check=False,
            cwd=cwd,
        )


def _empty_hint_dict() -> dict[str, dict[str, str]]:
    """Factory for empty hint dictionaries."""
    return {}


@dataclass(frozen=True, slots=True)
class Hints:
    """Installation hints organized by category and platform.

    Structure mirrors hints.toml:
        [tools.cmake]
        debian = "sudo apt install cmake"
        fedora = "sudo dnf install cmake"

        [system.sdl2]
        debian = "sudo apt install libsdl2-dev"

        [runtime.virmidi]
        linux = "sudo modprobe snd-virmidi"
    """

    tools: dict[str, dict[str, str]] = field(default_factory=_empty_hint_dict)
    system: dict[str, dict[str, str]] = field(default_factory=_empty_hint_dict)
    runtime: dict[str, dict[str, str]] = field(default_factory=_empty_hint_dict)

    def get_tool_hint(self, tool_id: str, platform_key: str) -> str | None:
        """Get installation hint for a tool."""
        tool_hints = self.tools.get(tool_id)
        if tool_hints:
            return tool_hints.get(platform_key)
        return None

    def get_system_hint(self, dep_id: str, platform_key: str) -> str | None:
        """Get installation hint for a system dependency."""
        dep_hints = self.system.get(dep_id)
        if dep_hints:
            return dep_hints.get(platform_key)
        return None

    def get_runtime_hint(self, key: str, platform_key: str) -> str | None:
        """Get hint for a runtime requirement."""
        runtime_hints = self.runtime.get(key)
        if runtime_hints:
            return runtime_hints.get(platform_key)
        return None

    @classmethod
    def empty(cls) -> "Hints":
        """Create empty hints."""
        return cls()


def load_hints(path: Path | None = None) -> Hints:
    """Load hints from TOML file.

    Args:
        path: Path to hints.toml. If None, uses default location.

    Returns:
        Hints dataclass with loaded data, or empty Hints on error.
    """
    if path is None:
        # Default: ms/data/hints.toml
        # From ms/services/checkers/common.py -> ms/services/checkers -> ms/services -> ms -> ms/data
        path = Path(__file__).parent.parent.parent / "data" / "hints.toml"

    if not path.exists():
        return Hints.empty()

    try:
        content = path.read_text(encoding="utf-8")
        data = tomllib.loads(content)

        return Hints(
            tools=_extract_section(data, "tools"),
            system=_extract_section(data, "system"),
            runtime=_extract_section(data, "runtime"),
        )
    except Exception:
        return Hints.empty()


def _extract_section(data: dict[str, object], section: str) -> dict[str, dict[str, str]]:
    """Extract a section from parsed TOML data.

    Example:
        data = {"tools": {"cmake": {"debian": "apt install cmake"}}}
        _extract_section(data, "tools") -> {"cmake": {"debian": "apt install cmake"}}
    """
    result: dict[str, dict[str, str]] = {}
    raw_section = data.get(section)

    if raw_section is None or not isinstance(raw_section, dict):
        return result

    # Cast to Any to work with dynamic TOML data
    section_dict = cast(dict[str, Any], raw_section)

    # Iterate over items (e.g., cmake, ninja, etc.)
    for item_key, item_value in section_dict.items():
        if not isinstance(item_value, dict):
            continue

        # Cast item to dict[str, Any]
        item_dict = cast(dict[str, Any], item_value)

        # Build hint dict for this item
        hint_dict: dict[str, str] = {}
        for platform_key, platform_value in item_dict.items():
            if platform_value is not None:
                hint_dict[platform_key] = str(platform_value)

        if hint_dict:
            result[item_key] = hint_dict

    return result


def get_platform_key(platform: "Platform", distro: "LinuxDistro | None" = None) -> str:
    """Get the hint key for a platform/distro combination.

    Args:
        platform: Current platform
        distro: Linux distribution (if on Linux)

    Returns:
        Key to use for hint lookup (e.g., "debian", "macos", "windows")
    """
    from ms.platform.detection import LinuxDistro, Platform

    match platform:
        case Platform.LINUX:
            if distro:
                match distro:
                    case LinuxDistro.DEBIAN:
                        return "debian"
                    case LinuxDistro.FEDORA:
                        return "fedora"
                    case LinuxDistro.ARCH:
                        return "arch"
                    case LinuxDistro.SUSE:
                        return "fedora"  # Close enough
                    case _:
                        return "debian"
            return "debian"
        case Platform.MACOS:
            return "macos"
        case Platform.WINDOWS:
            return "windows"
        case _:
            return "debian"


def first_line(text: str) -> str:
    """Extract first non-empty line from text.

    Useful for parsing version output from commands.
    """
    for line in text.strip().splitlines():
        stripped = line.strip()
        if stripped:
            return stripped
    return ""


# Import types for type hints only
if True:  # TYPE_CHECKING workaround for runtime imports
    from ms.platform.detection import LinuxDistro, Platform

    __all__ = [
        "CommandRunner",
        "DefaultCommandRunner",
        "Hints",
        "load_hints",
        "get_platform_key",
        "first_line",
        "Platform",
        "LinuxDistro",
    ]
