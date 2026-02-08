from __future__ import annotations

from pathlib import Path

from ms.core.workspace import Workspace
from ms.output.console import ConsoleProtocol

from .sync import RepoSyncMixin


class RepoService(RepoSyncMixin):
    """Clone/update all repos from a pinned manifest (git-only)."""

    def __init__(
        self,
        *,
        workspace: Workspace,
        console: ConsoleProtocol,
        manifest_path: Path | None = None,
    ) -> None:
        self._workspace = workspace
        self._console = console
        self._manifest_path = manifest_path or (
            Path(__file__).resolve().parents[2] / "data" / "repos.toml"
        )
