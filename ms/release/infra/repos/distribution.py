from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ms.core.result import Ok, Result
from ms.output.console import ConsoleProtocol
from ms.release.domain.config import DIST_DEFAULT_BRANCH, DIST_LOCAL_DIR, DIST_REPO_SLUG
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
class DistRepoPaths:
    root: Path


def ensure_distribution_repo(
    *,
    workspace_root: Path,
    console: ConsoleProtocol,
    dry_run: bool,
) -> Result[DistRepoPaths, ReleaseError]:
    result = ensure_repo_clone(
        workspace_root=workspace_root,
        local_dir=DIST_LOCAL_DIR,
        repo_slug=DIST_REPO_SLUG,
        clone_error_message="failed to clone distribution repo",
        console=console,
        dry_run=dry_run,
    )
    if isinstance(result, Ok):
        return Ok(DistRepoPaths(root=result.value))
    return result


def ensure_clean_git_repo(*, repo_root: Path) -> Result[None, ReleaseError]:
    return ensure_clean_git_repo_shared(
        repo_root=repo_root,
        repo_label="distribution",
        dirty_hint="Commit/stash changes in distribution/ then retry.",
    )


def checkout_main_and_pull(
    *,
    repo_root: Path,
    console: ConsoleProtocol,
    dry_run: bool,
) -> Result[None, ReleaseError]:
    return checkout_main_and_pull_shared(
        repo_root=repo_root,
        default_branch=DIST_DEFAULT_BRANCH,
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
) -> Result[None, ReleaseError]:
    result = commit_and_push_shared(
        repo_root=repo_root,
        branch=branch,
        paths=paths,
        message=message,
        console=console,
        dry_run=dry_run,
        return_head_sha=False,
    )
    if isinstance(result, Ok):
        return Ok(None)
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
        repo_slug=DIST_REPO_SLUG,
        base_branch=DIST_DEFAULT_BRANCH,
        branch=branch,
        title=title,
        body=body,
        repo_label="distribution",
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
        repo_slug=DIST_REPO_SLUG,
        pr_url=pr_url,
        repo_label="distribution",
        delete_branch=True,
        allow_auto_merge_fallback=False,
        console=console,
        dry_run=dry_run,
    )
