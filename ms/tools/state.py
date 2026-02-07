"""Tool state tracking - which versions are installed.

This module provides simple state management for tracking installed
tool versions. State is stored in tools/state.json.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

from ms.platform.files import atomic_write_text

__all__ = ["ToolState", "load_state", "save_state", "get_installed_version"]


@dataclass(frozen=True, slots=True)
class ToolState:
    """State of an installed tool.

    Attributes:
        version: Installed version string
        installed_at: ISO timestamp of installation
    """

    version: str
    installed_at: str

    @classmethod
    def now(cls, version: str) -> ToolState:
        """Create state with current timestamp."""
        return cls(version=version, installed_at=datetime.now().isoformat())


def _state_file(tools_dir: Path) -> Path:
    """Get path to state file."""
    return tools_dir / "state.json"


def load_state(tools_dir: Path) -> dict[str, ToolState]:
    """Load tool state from disk.

    Args:
        tools_dir: Tools directory containing state.json

    Returns:
        Dict mapping tool id to ToolState
    """
    state_path = _state_file(tools_dir)
    if not state_path.exists():
        return {}

    try:
        data = json.loads(state_path.read_text(encoding="utf-8"))
        return {tool_id: ToolState(**state_data) for tool_id, state_data in data.items()}
    except (json.JSONDecodeError, TypeError, KeyError):
        # Corrupted state file, start fresh
        return {}


def save_state(tools_dir: Path, state: dict[str, ToolState]) -> None:
    """Save tool state to disk.

    Args:
        tools_dir: Tools directory for state.json
        state: Dict mapping tool id to ToolState
    """
    state_path = _state_file(tools_dir)
    data = {tool_id: asdict(tool_state) for tool_id, tool_state in state.items()}
    atomic_write_text(state_path, json.dumps(data, indent=2), encoding="utf-8")


def get_installed_version(tools_dir: Path, tool_id: str) -> str | None:
    """Get installed version for a tool.

    Args:
        tools_dir: Tools directory
        tool_id: Tool identifier

    Returns:
        Version string or None if not installed
    """
    state = load_state(tools_dir)
    tool_state = state.get(tool_id)
    return tool_state.version if tool_state else None


def set_installed_version(tools_dir: Path, tool_id: str, version: str) -> None:
    """Set installed version for a tool.

    Args:
        tools_dir: Tools directory
        tool_id: Tool identifier
        version: Version string
    """
    state = load_state(tools_dir)
    state[tool_id] = ToolState.now(version)
    save_state(tools_dir, state)
