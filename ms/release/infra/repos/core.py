from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ms.core.result import Err, Ok, Result
from ms.output.console import ConsoleProtocol
from ms.release.domain.config import CORE_DEFAULT_BRANCH, CORE_LOCAL_DIR, CORE_REPO_SLUG
from ms.release.errors import ReleaseError
from ms.release.infra.github.pr_merge import create_pull_request, merge_pull_request
from ms.release.infra.repos.git_ops import (
    checkout_main_and_pull as checkout_main_and_pull_shared,
)
from ms.release.infra.repos.git_ops import (
    commit_and_push as commit_and_push_shared,
)
from ms.release.infra.repos.git_ops import (
    create_branch as create_branch_shared,
)
from ms.release.infra.repos.git_ops import (
    ensure_clean_git_repo as ensure_clean_git_repo_shared,
)


@dataclass(frozen=True, slots=True)
class CoreRepoPaths:
    root: Path


def ensure_core_repo(
    *,
    workspace_root: Path,
    console: ConsoleProtocol,
    dry_run: bool,
) -> Result[CoreRepoPaths, ReleaseError]:
    del console, dry_run
    repo_root = workspace_root / CORE_LOCAL_DIR
    if repo_root.is_dir() and (repo_root / ".git").exists():
        return Ok(CoreRepoPaths(root=repo_root))

    return Err(
        ReleaseError(
            kind="invalid_input",
            message=f"core repo is unavailable: {repo_root}",
            hint="Run: uv run ms sync --repos",
        )
    )


def ensure_clean_git_repo(*, repo_root: Path) -> Result[None, ReleaseError]:
    return ensure_clean_git_repo_shared(
        repo_root=repo_root,
        repo_label="core",
        dirty_hint="Commit/stash changes in midi-studio/core then retry.",
    )


def checkout_main_and_pull(
    *,
    repo_root: Path,
    console: ConsoleProtocol,
    dry_run: bool,
) -> Result[None, ReleaseError]:
    return checkout_main_and_pull_shared(
        repo_root=repo_root,
        default_branch=CORE_DEFAULT_BRANCH,
        console=console,
        dry_run=dry_run,
    )


def create_branch(
    *,
    repo_root: Path,
    branch: str,
    console: ConsoleProtocol,
    dry_run: bool,
) -> Result[None, ReleaseError]:
    return create_branch_shared(
        repo_root=repo_root,
        branch=branch,
        base_sha=None,
        console=console,
        dry_run=dry_run,
    )


def commit_and_push(
    *,
    repo_root: Path,
    branch: str,
    paths: list[Path],
    message: str,
    console: ConsoleProtocol,
    dry_run: bool,
) -> Result[str, ReleaseError]:
    result = commit_and_push_shared(
        repo_root=repo_root,
        branch=branch,
        paths=paths,
        message=message,
        console=console,
        dry_run=dry_run,
        return_head_sha=True,
        head_sha_read_error="failed to read core branch head sha",
        head_sha_invalid_error="invalid core branch head sha",
    )
    if isinstance(result, Ok):
        value = result.value
        if isinstance(value, str):
            return Ok(value)
        return Err(
            ReleaseError(
                kind="repo_failed",
                message="missing core branch head sha",
            )
        )
    return result


def open_pr(
    *,
    workspace_root: Path,
    branch: str,
    title: str,
    body: str,
    console: ConsoleProtocol,
    dry_run: bool,
) -> Result[str, ReleaseError]:
    return create_pull_request(
        workspace_root=workspace_root,
        repo_slug=CORE_REPO_SLUG,
        base_branch=CORE_DEFAULT_BRANCH,
        branch=branch,
        title=title,
        body=body,
        repo_label="core",
        console=console,
        dry_run=dry_run,
    )


def merge_pr(
    *,
    workspace_root: Path,
    pr_url: str,
    console: ConsoleProtocol,
    dry_run: bool,
) -> Result[None, ReleaseError]:
    return merge_pull_request(
        workspace_root=workspace_root,
        repo_slug=CORE_REPO_SLUG,
        pr_url=pr_url,
        repo_label="core",
        delete_branch=True,
        allow_auto_merge_fallback=True,
        console=console,
        dry_run=dry_run,
    )
