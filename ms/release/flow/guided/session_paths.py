from __future__ import annotations

from pathlib import Path


def sessions_root(*, workspace_root: Path) -> Path:
    return workspace_root / ".ms" / "release" / "sessions"


def app_session_path(*, workspace_root: Path) -> Path:
    return sessions_root(workspace_root=workspace_root) / "app-release.json"


def content_session_path(*, workspace_root: Path) -> Path:
    return sessions_root(workspace_root=workspace_root) / "content-release.json"
