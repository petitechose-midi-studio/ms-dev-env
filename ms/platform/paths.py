"""Platform-aware path utilities.

This module provides functions for locating user-level directories
(home, global config). Workspace-specific paths (tools, cache) are
in core/workspace.py.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from .detection import is_windows

__all__ = [
    "home",
    "user_config_dir",
]

# Application name used for directory naming
APP_NAME = "ms"


@lru_cache(maxsize=1)
def home() -> Path:
    """Get user's home directory.

    Uses USERPROFILE on Windows, HOME on Unix.
    Falls back to Path.home() which handles edge cases.
    """
    # Check env vars first for CI/container scenarios
    if is_windows():
        userprofile = os.environ.get("USERPROFILE")
        if userprofile:
            return Path(userprofile)
    else:
        home_env = os.environ.get("HOME")
        if home_env:
            return Path(home_env)

    # Fallback to Python's home detection
    return Path.home()


@lru_cache(maxsize=1)
def user_config_dir() -> Path:
    """Get the user-level configuration directory.

    This is for global user preferences (e.g., mode=dev/enduser).
    Location: ~/.config/ms/ (Linux/macOS) or ~/AppData/Roaming/ms/ (Windows)

    Note: Workspace-specific config is in workspace/config.toml.
    """
    if is_windows():
        app_data = os.environ.get("APPDATA")
        if app_data:
            return Path(app_data) / APP_NAME
        return home() / "AppData" / "Roaming" / APP_NAME

    # Unix: XDG_CONFIG_HOME or ~/.config
    xdg_config = os.environ.get("XDG_CONFIG_HOME")
    if xdg_config:
        return Path(xdg_config) / APP_NAME
    return home() / ".config" / APP_NAME


def clear_caches() -> None:
    """Clear all cached paths.

    Useful for testing when environment variables change.
    """
    home.cache_clear()
    user_config_dir.cache_clear()
