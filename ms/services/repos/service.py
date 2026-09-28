from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from ms.core.result import Err, Ok, Result
from ms.core.workspace import Workspace
from ms.output.console import ConsoleProtocol, Style
from ms.platform.detection import Platform, detect_platform

from .lockfile import write_lock_file
from .manifest import load_manifests
from .models import RepoError, RepoLockEntry
from .ms_manager_artifacts import (
    MS_MANAGER_DEV_ARTIFACTS_FILE,
    MS_MANAGER_REPO_PATH,
    write_ms_manager_dev_artifacts,
)
from .sync import RepoSync


class RepoService:
    """Clone/update all repos from a pinned manifest (git-only)."""

    def __init__(
        self,
        *,
        workspace: Workspace,
        console: ConsoleProtocol,
        manifest_paths: Sequence[Path] | None = None,
        platform: Platform | None = None,
    ) -> None:
        self._workspace = workspace
        self._console = console
        self._platform = platform or detect_platform()
        self._manifest_paths = (
            tuple(manifest_paths)
            if manifest_paths is not None
            else (Path(__file__).resolve().parents[2] / "data" / "repos.toml",)
        )
        self._sync = RepoSync(workspace=workspace, console=console)

    def sync_all(self, *, dry_run: bool = False) -> Result[None, RepoError]:
        specs_result = load_manifests(self._manifest_paths)
        if isinstance(specs_result, Err):
            return specs_result
        specs = specs_result.value

        lock: list[RepoLockEntry] = []
        has_errors = False
        for spec in specs:
            entry = self._sync.sync_repo(spec, dry_run=dry_run)
            if entry is None:
                has_errors = True
                continue
            lock.append(entry)

        if not dry_run:
            write_lock_file(workspace=self._workspace, lock=lock)

        if any(Path(spec.path).as_posix().rstrip("/") == MS_MANAGER_REPO_PATH for spec in specs):
            config_path = (
                self._workspace.root / MS_MANAGER_REPO_PATH / MS_MANAGER_DEV_ARTIFACTS_FILE
            )
            if dry_run or config_path.parent.is_dir():
                self._console.print(f"generate {config_path}", Style.DIM)
            if not dry_run and config_path.parent.is_dir():
                try:
                    write_ms_manager_dev_artifacts(
                        workspace=self._workspace, platform=self._platform,
                    )
                except OSError as error:
                    return Err(
                        RepoError(
                            kind="sync_failed",
                            message=f"failed to generate {config_path}: {error}",
                        )
                    )

        if has_errors:
            return Err(
                RepoError(kind="sync_failed", message="some repositories failed to sync")
            )
        return Ok(None)
