"""Workspace detection and paths.

The workspace is the root directory of the MIDI Studio environment.

It is identified by the presence of a `.ms-workspace` marker file.

Rationale:
- Avoid coupling workspace detection to legacy directories (e.g. `commands/`).
- Keep detection stable even as the workspace layout evolves.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from .result import Err, Ok, Result

__all__ = [
    "Workspace",
    "WorkspaceError",
    "detect_workspace",
]


@dataclass(frozen=True)
class WorkspaceError:
    """Error when workspace cannot be detected."""

    message: str
    searched_from: Path | None = None


@dataclass(frozen=True, slots=True)
class Workspace:
    """Represents a detected MIDI Studio workspace.

    The workspace root contains:
    - .ms-workspace marker file (required)
    - config.toml (optional)
    - open-control/ and midi-studio/ repos (dev mode)
    - tools/ and bin/ generated artifacts (gitignored)
    """

    root: Path

    @property
    def config_path(self) -> Path:
        """Path to config.toml."""
        return self.root / "config.toml"

    @property
    def marker_path(self) -> Path:
        """Path to the workspace marker file."""
        return self.root / ".ms-workspace"

    @property
    def state_dir(self) -> Path:
        """Path to workspace state directory (.ms/)."""
        return self.root / ".ms"

    @property
    def state_path(self) -> Path:
        """Path to workspace state file (.ms/state.toml)."""
        return self.state_dir / "state.toml"

    @property
    def bin_dir(self) -> Path:
        """Path to bin output directory."""
        return self.root / "bin"

    @property
    def build_dir(self) -> Path:
        """Path to build directory."""
        return self.root / ".build"

    @property
    def tools_dir(self) -> Path:
        """Path to tools directory (cmake, zig, etc.)."""
        return self.root / "tools"

    @property
    def tools_bin_dir(self) -> Path:
        """Path to tools/bin directory (wrappers)."""
        return self.root / "tools" / "bin"

    @property
    def cache_dir(self) -> Path:
        """Path to local cache directory (downloads, temp files).

        Location: workspace/.ms/cache/
        This directory should be in .gitignore.
        """
        return self.state_dir / "cache"

    @property
    def download_cache_dir(self) -> Path:
        """Path to download cache directory.

        Location: workspace/.ms/cache/downloads/
        Archives are cached here to avoid re-downloading.
        """
        return self.cache_dir / "downloads"

    @property
    def open_control_dir(self) -> Path:
        """Path to open-control project."""
        return self.root / "open-control"

    @property
    def midi_studio_dir(self) -> Path:
        """Path to midi-studio project."""
        return self.root / "midi-studio"

    def exists(self) -> bool:
        """Check if this workspace still exists on disk."""
        return self.root.is_dir() and self.marker_path.exists()

    def __str__(self) -> str:
        return str(self.root)


def _is_workspace_root(path: Path) -> bool:
    """Check if a path is a workspace root.

    A workspace root must have:
    - .ms-workspace marker file
    """
    return (path / ".ms-workspace").is_file()


def _find_workspace_upward(start: Path) -> Path | None:
    """Search upward from start directory for a workspace root.

    Returns the workspace root path if found, None otherwise.
    """
    for parent in (start, *start.parents):
        if _is_workspace_root(parent):
            return parent
    return None


def detect_workspace(
    *,
    start_dir: Path | None = None,
    env_var: str = "WORKSPACE_ROOT",
) -> Result[Workspace, WorkspaceError]:
    """Detect the workspace root directory.

    Detection order:
    1. WORKSPACE_ROOT environment variable (if set and valid)
    2. Search upward from start_dir (or cwd) for workspace markers

    Args:
        start_dir: Directory to start searching from (defaults to cwd)
        env_var: Environment variable name to check (defaults to WORKSPACE_ROOT)

    Returns:
        Ok(Workspace) if found, Err(WorkspaceError) if not found.
    """
    # Try environment variable first
    env_value = os.environ.get(env_var)
    if env_value:
        env_path = Path(env_value).expanduser().resolve()
        if env_path.is_dir() and _is_workspace_root(env_path):
            return Ok(Workspace(root=env_path))
        # Environment variable set but invalid - this is an error, not a fallback
        return Err(
            WorkspaceError(
                message=f"${env_var} is set to '{env_value}' but it is not a valid workspace",
                searched_from=env_path if env_path.is_dir() else None,
            )
        )

    # Search upward from start directory
    search_start = start_dir or Path.cwd()
    search_start = search_start.resolve()

    found = _find_workspace_upward(search_start)
    if found:
        return Ok(Workspace(root=found))

    return Err(
        WorkspaceError(
            message="Could not find workspace (.ms-workspace not found)",
            searched_from=search_start,
        )
    )


def detect_workspace_or_raise(
    *,
    start_dir: Path | None = None,
    env_var: str = "WORKSPACE_ROOT",
) -> Workspace:
    """Detect workspace, raising ValueError if not found.

    This is a convenience function for scripts that want to fail fast
    rather than handle Result types.

    Raises:
        ValueError: If workspace cannot be detected
    """
    result = detect_workspace(start_dir=start_dir, env_var=env_var)
    if isinstance(result, Err):
        raise ValueError(result.error.message)
    return result.value
