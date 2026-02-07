from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ms.core.result import Err, Ok, Result
from ms.output.console import ConsoleProtocol, Style
from ms.platform.process import run as run_process
from ms.services.release.config import DIST_DEFAULT_BRANCH, DIST_LOCAL_DIR, DIST_REPO_SLUG
from ms.services.release.errors import ReleaseError
from ms.services.release.pr_orchestration import create_pull_request, merge_pull_request
from ms.services.release.timeouts import (
    GH_CLONE_TIMEOUT_SECONDS,
    GIT_NETWORK_TIMEOUT_SECONDS,
    GIT_TIMEOUT_SECONDS,
)


def _run_git_command(*, cmd: list[str], repo_root: Path, network: bool = False):
    timeout = GIT_NETWORK_TIMEOUT_SECONDS if network else GIT_TIMEOUT_SECONDS
    return run_process(cmd, cwd=repo_root, timeout=timeout)


@dataclass(frozen=True, slots=True)
class DistRepoPaths:
    root: Path


def ensure_distribution_repo(
    *,
    workspace_root: Path,
    console: ConsoleProtocol,
    dry_run: bool,
) -> Result[DistRepoPaths, ReleaseError]:
    repo_root = workspace_root / DIST_LOCAL_DIR
    if repo_root.is_dir() and (repo_root / ".git").is_dir():
        return Ok(DistRepoPaths(root=repo_root))

    console.print(f"clone {DIST_REPO_SLUG} -> {repo_root}", Style.DIM)
    if dry_run:
        return Ok(DistRepoPaths(root=repo_root))

    repo_root.parent.mkdir(parents=True, exist_ok=True)
    result = run_process(
        ["gh", "repo", "clone", DIST_REPO_SLUG, str(repo_root)],
        cwd=workspace_root,
        timeout=GH_CLONE_TIMEOUT_SECONDS,
    )
    if isinstance(result, Err):
        e = result.error
        return Err(
            ReleaseError(
                kind="dist_repo_failed",
                message="failed to clone distribution repo",
                hint=e.stderr.strip() or None,
            )
        )

    return Ok(DistRepoPaths(root=repo_root))


def ensure_clean_git_repo(*, repo_root: Path) -> Result[None, ReleaseError]:
    result = _run_git_command(cmd=["git", "status", "--porcelain"], repo_root=repo_root)
    if isinstance(result, Err):
        e = result.error
        return Err(
            ReleaseError(
                kind="dist_repo_failed",
                message="failed to check git status",
                hint=e.stderr.strip() or None,
            )
        )

    if result.value.strip():
        return Err(
            ReleaseError(
                kind="dist_repo_dirty",
                message=f"distribution repo is dirty: {repo_root}",
                hint="Commit/stash changes in distribution/ then retry.",
            )
        )

    return Ok(None)


def checkout_main_and_pull(
    *,
    repo_root: Path,
    console: ConsoleProtocol,
    dry_run: bool,
) -> Result[None, ReleaseError]:
    console.print(f"git checkout {DIST_DEFAULT_BRANCH}", Style.DIM)
    console.print("git pull --ff-only", Style.DIM)
    if dry_run:
        return Ok(None)

    for cmd in (
        ["git", "checkout", DIST_DEFAULT_BRANCH],
        ["git", "pull", "--ff-only", "origin", DIST_DEFAULT_BRANCH],
    ):
        result = _run_git_command(cmd=cmd, repo_root=repo_root, network=cmd[1] == "pull")
        if isinstance(result, Err):
            e = result.error
            return Err(
                ReleaseError(
                    kind="dist_repo_failed",
                    message=f"git failed: {' '.join(cmd[:3])}",
                    hint=e.stderr.strip() or None,
                )
            )

    return Ok(None)


def create_branch(
    *,
    repo_root: Path,
    branch: str,
    console: ConsoleProtocol,
    dry_run: bool,
) -> Result[None, ReleaseError]:
    console.print(f"git checkout -b {branch}", Style.DIM)
    if dry_run:
        return Ok(None)

    result = _run_git_command(cmd=["git", "checkout", "-b", branch], repo_root=repo_root)
    if isinstance(result, Err):
        e = result.error
        return Err(
            ReleaseError(
                kind="dist_repo_failed",
                message=f"failed to create branch: {branch}",
                hint=e.stderr.strip() or None,
            )
        )
    return Ok(None)


def commit_and_push(
    *,
    repo_root: Path,
    branch: str,
    paths: list[Path],
    message: str,
    console: ConsoleProtocol,
    dry_run: bool,
) -> Result[None, ReleaseError]:
    rels = [str(p.relative_to(repo_root)) for p in paths]
    console.print(f"git add -A -- {' '.join(rels)}", Style.DIM)
    console.print(f"git commit -m {message}", Style.DIM)
    console.print(f"git push -u origin {branch}", Style.DIM)

    if dry_run:
        return Ok(None)

    add = _run_git_command(cmd=["git", "add", "-A", "--", *rels], repo_root=repo_root)
    if isinstance(add, Err):
        e = add.error
        return Err(
            ReleaseError(
                kind="dist_repo_failed",
                message="git add failed",
                hint=e.stderr.strip() or None,
            )
        )

    commit = _run_git_command(cmd=["git", "commit", "-m", message], repo_root=repo_root)
    if isinstance(commit, Err):
        e = commit.error
        hint = e.stderr.strip() or None
        if hint is None:
            hint = "Configure git user.name/user.email, then retry."
        return Err(
            ReleaseError(
                kind="dist_repo_failed",
                message="git commit failed",
                hint=hint,
            )
        )

    push = _run_git_command(
        cmd=["git", "push", "-u", "origin", branch],
        repo_root=repo_root,
        network=True,
    )
    if isinstance(push, Err):
        e = push.error
        return Err(
            ReleaseError(
                kind="dist_repo_failed",
                message="git push failed",
                hint=e.stderr.strip() or None,
            )
        )

    return Ok(None)


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
