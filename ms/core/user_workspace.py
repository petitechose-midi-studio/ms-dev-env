"""User-level default workspace selection.

This module stores a single "default workspace" path for `ms` so that `ms` is
useful even when invoked outside the workspace tree.

Storage location is platform-specific (see `ms.platform.paths.user_config_dir`).
The file is intentionally small and dedicated:

  <user-config-dir>/workspace.toml

with content like:

  workspace_root = "C:/Users/name/workspace"
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ms.core.result import Err, Ok, Result
from ms.platform.paths import user_config_dir

__all__ = [
    "UserWorkspaceError",
    "forget_default_workspace_root",
    "get_default_workspace_root",
    "remember_default_workspace_root",
    "user_workspace_config_path",
]


@dataclass(frozen=True, slots=True)
class UserWorkspaceError:
    message: str
    path: Path | None = None


def user_workspace_config_path() -> Path:
    return user_config_dir() / "workspace.toml"


def _parse_toml(path: Path) -> Result[dict[str, Any], UserWorkspaceError]:
    try:
        raw = path.read_bytes()
    except FileNotFoundError:
        return Ok({})
    except PermissionError:
        return Err(UserWorkspaceError(f"Permission denied reading: {path}", path=path))
    except OSError as e:
        return Err(UserWorkspaceError(f"Error reading {path}: {e}", path=path))

    try:
        data = tomllib.loads(raw.decode("utf-8"))
    except tomllib.TOMLDecodeError as e:
        return Err(UserWorkspaceError(f"Invalid TOML syntax: {e}", path=path))
    except UnicodeDecodeError as e:
        return Err(UserWorkspaceError(f"Invalid UTF-8 in config: {e}", path=path))
    except Exception as e:  # noqa: BLE001
        return Err(UserWorkspaceError(f"Error parsing config: {e}", path=path))

    # tomllib guarantees the top-level is a mapping.
    return Ok(data)


def get_default_workspace_root() -> Result[Path | None, UserWorkspaceError]:
    """Return the remembered default workspace root, if configured."""
    path = user_workspace_config_path()
    result = _parse_toml(path)
    if isinstance(result, Err):
        return result

    root = result.value.get("workspace_root")
    if root is None:
        return Ok(None)
    if not isinstance(root, str) or not root.strip():
        return Err(UserWorkspaceError("workspace_root must be a non-empty string", path=path))

    try:
        return Ok(Path(root).expanduser().resolve())
    except OSError as e:
        return Err(UserWorkspaceError(f"Invalid workspace_root path: {e}", path=path))


def remember_default_workspace_root(root: Path) -> Result[None, UserWorkspaceError]:
    """Persist the default workspace root."""
    config_path = user_workspace_config_path()
    try:
        config_path.parent.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        return Err(
            UserWorkspaceError(f"Could not create {config_path.parent}: {e}", path=config_path)
        )

    resolved = root.expanduser().resolve()
    stored = resolved.as_posix()
    content = f'workspace_root = "{stored}"\n'
    try:
        config_path.write_text(content, encoding="utf-8", newline="\n")
    except OSError as e:
        return Err(UserWorkspaceError(f"Could not write {config_path}: {e}", path=config_path))
    return Ok(None)


def forget_default_workspace_root() -> Result[None, UserWorkspaceError]:
    """Remove the remembered default workspace root."""
    config_path = user_workspace_config_path()
    try:
        config_path.unlink(missing_ok=True)
    except OSError as e:
        return Err(UserWorkspaceError(f"Could not remove {config_path}: {e}", path=config_path))
    return Ok(None)
