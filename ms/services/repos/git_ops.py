from __future__ import annotations

from pathlib import Path

from ms.core.result import Err, Ok, Result
from ms.git.sha import is_git_sha
from ms.platform.process import ProcessError
from ms.platform.process import run as run_process

_GIT_TIMEOUT_SECONDS = 30.0
_GIT_NETWORK_TIMEOUT_SECONDS = 3 * 60.0


def run_git(
    cmd: list[str], *, cwd: Path, network: bool = False
) -> Result[str, ProcessError]:
    timeout = _GIT_NETWORK_TIMEOUT_SECONDS if network else _GIT_TIMEOUT_SECONDS
    return run_process(cmd, cwd=cwd, timeout=timeout)


def is_dirty(repo_dir: Path) -> bool | None:
    """Return True/False when git answered, None when inspection failed."""
    result = run_git(
        ["git", "-C", str(repo_dir), "status", "--porcelain"], cwd=repo_dir,
    )
    match result:
        case Ok(stdout):
            return bool(stdout.strip())
        case Err(_):
            return None


def current_branch(repo_dir: Path) -> str | None:
    result = run_git(
        ["git", "-C", str(repo_dir), "rev-parse", "--abbrev-ref", "HEAD"], cwd=repo_dir,
    )
    match result:
        case Ok(stdout):
            value = stdout.strip()
            return value or None
        case Err(_):
            return None


def head_sha(repo_dir: Path) -> str | None:
    result = run_git(["git", "-C", str(repo_dir), "rev-parse", "HEAD"], cwd=repo_dir)
    match result:
        case Ok(stdout):
            value = stdout.strip()
            return value if is_git_sha(value) else None
        case Err(_):
            return None
