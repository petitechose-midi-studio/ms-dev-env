from __future__ import annotations

from pathlib import Path

from ms.core.result import Err, Ok
from ms.platform.process import run as run_process

from ._context import RepoContextBase

_GIT_TIMEOUT_SECONDS = 30.0
_GIT_NETWORK_TIMEOUT_SECONDS = 3 * 60.0


class RepoGitOpsMixin(RepoContextBase):
    def _run_git(self, cmd: list[str], *, cwd: Path, network: bool = False):
        timeout = _GIT_NETWORK_TIMEOUT_SECONDS if network else _GIT_TIMEOUT_SECONDS
        return run_process(cmd, cwd=cwd, timeout=timeout)

    def _is_dirty(self, repo_dir: Path) -> bool:
        result = self._run_git(
            ["git", "-C", str(repo_dir), "status", "--porcelain"],
            cwd=repo_dir,
        )
        match result:
            case Ok(stdout):
                return bool(stdout.strip())
            case Err(_):
                return False
            case _:
                return False

    def _current_branch(self, repo_dir: Path) -> str | None:
        result = self._run_git(
            ["git", "-C", str(repo_dir), "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=repo_dir,
        )
        match result:
            case Ok(stdout):
                value = stdout.strip()
                return value or None
            case Err(_):
                return None

    def _head_sha(self, repo_dir: Path) -> str | None:
        result = self._run_git(
            ["git", "-C", str(repo_dir), "rev-parse", "HEAD"],
            cwd=repo_dir,
        )
        match result:
            case Ok(stdout):
                value = stdout.strip()
                return value or None
            case Err(_):
                return None
