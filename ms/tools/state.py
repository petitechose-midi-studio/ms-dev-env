"""Tool state tracking - which versions are installed.

This module provides simple state management for tracking installed
tool versions. State is stored in tools/state.json.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

from ms.core.result import Err, Ok, Result
from ms.core.structured import as_str_dict, get_str
from ms.platform.files import atomic_write_text

__all__ = [
    "ToolState",
    "StateError",
    "load_state",
    "save_state",
    "get_installed_version",
    "set_installed_version",
]


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


@dataclass(frozen=True, slots=True)
class StateError:
    """Error when the tool state file cannot be read or written."""

    message: str
    path: Path


def _state_file(tools_dir: Path) -> Path:
    """Get path to state file."""
    return tools_dir / "state.json"


def load_state(tools_dir: Path) -> Result[dict[str, ToolState], StateError]:
    """Load tool state from disk.

    Missing or corrupted state starts fresh (``Ok({})``). An unreadable file
    (permissions, encoding) is reported as a ``StateError`` so it is never
    mistaken for "no tools installed".

    Args:
        tools_dir: Tools directory containing state.json

    Returns:
        Ok(dict) mapping tool id to ToolState, or Err(StateError)
    """
    state_path = _state_file(tools_dir)
    if not state_path.exists():
        return Ok({})

    try:
        text = state_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        return Err(StateError(message=f"cannot read tool state: {exc}", path=state_path))

    try:
        data: object = json.loads(text)
    except json.JSONDecodeError:
        # Corrupted state file, start fresh
        return Ok({})

    table = as_str_dict(data)
    if table is None:
        return Ok({})

    parsed: dict[str, ToolState] = {}
    for tool_id, item in table.items():
        entry = as_str_dict(item)
        if entry is None:
            # Corrupted state file, start fresh
            return Ok({})
        version = get_str(entry, "version")
        installed_at = get_str(entry, "installed_at")
        if version is None or installed_at is None:
            # Corrupted state file, start fresh
            return Ok({})
        parsed[tool_id] = ToolState(version=version, installed_at=installed_at)
    return Ok(parsed)


def save_state(tools_dir: Path, state: dict[str, ToolState]) -> None:
    """Save tool state to disk.

    Args:
        tools_dir: Tools directory for state.json
        state: Dict mapping tool id to ToolState
    """
    state_path = _state_file(tools_dir)
    data = {tool_id: asdict(tool_state) for tool_id, tool_state in state.items()}
    atomic_write_text(state_path, json.dumps(data, indent=2), encoding="utf-8")


def get_installed_version(
    tools_dir: Path, tool_id: str
) -> Result[str | None, StateError]:
    """Get installed version for a tool.

    Args:
        tools_dir: Tools directory
        tool_id: Tool identifier

    Returns:
        Ok(version), Ok(None) if not installed, or Err(StateError) when unreadable
    """
    loaded = load_state(tools_dir)
    if isinstance(loaded, Err):
        return loaded
    tool_state = loaded.value.get(tool_id)
    return Ok(tool_state.version if tool_state else None)


def set_installed_version(
    tools_dir: Path, tool_id: str, version: str
) -> Result[None, StateError]:
    """Set installed version for a tool.

    Args:
        tools_dir: Tools directory
        tool_id: Tool identifier
        version: Version string

    Returns:
        Ok(None) on success, Err(StateError) when state cannot be read or written
    """
    loaded = load_state(tools_dir)
    if isinstance(loaded, Err):
        return loaded

    state = dict(loaded.value)
    state[tool_id] = ToolState.now(version)
    try:
        save_state(tools_dir, state)
    except OSError as exc:
        return Err(
            StateError(message=f"cannot write tool state: {exc}", path=_state_file(tools_dir))
        )
    return Ok(None)
