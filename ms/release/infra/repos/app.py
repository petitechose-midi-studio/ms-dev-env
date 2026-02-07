from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ms.core.result import Err, Ok, Result
from ms.output.console import ConsoleProtocol
from ms.release.domain.config import APP_DEFAULT_BRANCH, APP_LOCAL_DIR, APP_REPO_SLUG
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
from ms.release.infra.repos.git_ops import ensure_repo_clone


@dataclass(frozen=True, slots=True)
class AppRepoPaths:
    root: Path


def ensure_app_repo(
    *,
    workspace_root: Path,
    console: ConsoleProtocol,
    dry_run: bool,
) -> Result[AppRepoPaths, ReleaseError]:
    result = ensure_repo_clone(
        workspace_root=workspace_root,
        local_dir=APP_LOCAL_DIR,
        repo_slug=APP_REPO_SLUG,
        clone_error_message="failed to clone app repo",
        console=console,
        dry_run=dry_run,
    )
    if isinstance(result, Ok):
        return Ok(AppRepoPaths(root=result.value))
    return result


def ensure_clean_git_repo(*, repo_root: Path) -> Result[None, ReleaseError]:
    return ensure_clean_git_repo_shared(
        repo_root=repo_root,
        repo_label="app",
        dirty_hint="Commit/stash changes in ms-manager/ then retry.",
    )


def checkout_main_and_pull(
    *,
    repo_root: Path,
    console: ConsoleProtocol,
    dry_run: bool,
) -> Result[None, ReleaseError]:
    return checkout_main_and_pull_shared(
        repo_root=repo_root,
        default_branch=APP_DEFAULT_BRANCH,
        console=console,
        dry_run=dry_run,
    )


def create_branch(
    *,
    repo_root: Path,
    branch: str,
    base_sha: str | None,
    console: ConsoleProtocol,
    dry_run: bool,
) -> Result[None, ReleaseError]:
    return create_branch_shared(
        repo_root=repo_root,
        branch=branch,
        base_sha=base_sha,
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
        head_sha_read_error="failed to read app branch head sha",
        head_sha_invalid_error="invalid app branch head sha",
    )
    if isinstance(result, Ok):
        value = result.value
        if isinstance(value, str):
            return Ok(value)
        return Err(
            ReleaseError(
                kind="dist_repo_failed",
                message="missing app branch head sha",
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
        repo_slug=APP_REPO_SLUG,
        base_branch=APP_DEFAULT_BRANCH,
        branch=branch,
        title=title,
        body=body,
        repo_label="app",
        console=console,
        dry_run=dry_run,
    )


def merge_pr(
    *,
    workspace_root: Path,
    pr_url: str,
    delete_branch: bool,
    console: ConsoleProtocol,
    dry_run: bool,
) -> Result[None, ReleaseError]:
    return merge_pull_request(
        workspace_root=workspace_root,
        repo_slug=APP_REPO_SLUG,
        pr_url=pr_url,
        repo_label="app",
        delete_branch=delete_branch,
        allow_auto_merge_fallback=True,
        console=console,
        dry_run=dry_run,
    )
