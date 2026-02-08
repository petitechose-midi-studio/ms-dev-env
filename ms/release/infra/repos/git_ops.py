from __future__ import annotations

from pathlib import Path

from ms.core.result import Err, Ok, Result
from ms.output.console import ConsoleProtocol, Style
from ms.platform.process import run as run_process
from ms.release.errors import ReleaseError
from ms.release.infra.github.timeouts import (
    GH_CLONE_TIMEOUT_SECONDS,
    GIT_NETWORK_TIMEOUT_SECONDS,
    GIT_TIMEOUT_SECONDS,
)


def run_git_command(*, cmd: list[str], repo_root: Path, network: bool = False):
    timeout = GIT_NETWORK_TIMEOUT_SECONDS if network else GIT_TIMEOUT_SECONDS
    return run_process(cmd, cwd=repo_root, timeout=timeout)


def ensure_repo_clone(
    *,
    workspace_root: Path,
    local_dir: str,
    repo_slug: str,
    clone_error_message: str,
    console: ConsoleProtocol,
    dry_run: bool,
) -> Result[Path, ReleaseError]:
    repo_root = workspace_root / local_dir
    if repo_root.is_dir() and (repo_root / ".git").is_dir():
        return Ok(repo_root)

    console.print(f"clone {repo_slug} -> {repo_root}", Style.DIM)
    if dry_run:
        return Ok(repo_root)

    repo_root.parent.mkdir(parents=True, exist_ok=True)
    result = run_process(
        ["gh", "repo", "clone", repo_slug, str(repo_root)],
        cwd=workspace_root,
        timeout=GH_CLONE_TIMEOUT_SECONDS,
    )
    if isinstance(result, Err):
        e = result.error
        return Err(
            ReleaseError(
                kind="repo_failed",
                message=clone_error_message,
                hint=e.stderr.strip() or None,
            )
        )

    return Ok(repo_root)


def ensure_clean_git_repo(
    *,
    repo_root: Path,
    repo_label: str,
    dirty_hint: str,
) -> Result[None, ReleaseError]:
    result = run_git_command(cmd=["git", "status", "--porcelain"], repo_root=repo_root)
    if isinstance(result, Err):
        e = result.error
        return Err(
            ReleaseError(
                kind="repo_failed",
                message="failed to check git status",
                hint=e.stderr.strip() or None,
            )
        )

    if result.value.strip():
        return Err(
            ReleaseError(
                kind="repo_dirty",
                message=f"{repo_label} repo is dirty: {repo_root}",
                hint=dirty_hint,
            )
        )

    return Ok(None)


def checkout_main_and_pull(
    *,
    repo_root: Path,
    default_branch: str,
    console: ConsoleProtocol,
    dry_run: bool,
) -> Result[None, ReleaseError]:
    console.print(f"git checkout {default_branch}", Style.DIM)
    console.print("git pull --ff-only", Style.DIM)
    if dry_run:
        return Ok(None)

    for cmd in (
        ["git", "checkout", default_branch],
        ["git", "pull", "--ff-only", "origin", default_branch],
    ):
        result = run_git_command(cmd=cmd, repo_root=repo_root, network=cmd[1] == "pull")
        if isinstance(result, Err):
            e = result.error
            return Err(
                ReleaseError(
                    kind="repo_failed",
                    message=f"git failed: {' '.join(cmd[:3])}",
                    hint=e.stderr.strip() or None,
                )
            )

    return Ok(None)


def create_branch(
    *,
    repo_root: Path,
    branch: str,
    base_sha: str | None,
    console: ConsoleProtocol,
    dry_run: bool,
) -> Result[None, ReleaseError]:
    if base_sha is not None:
        console.print(f"git checkout -b {branch} {base_sha}", Style.DIM)
    else:
        console.print(f"git checkout -b {branch}", Style.DIM)
    if dry_run:
        return Ok(None)

    cmd = ["git", "checkout", "-b", branch]
    if base_sha is not None:
        cmd.append(base_sha)

    result = run_git_command(cmd=cmd, repo_root=repo_root)
    if isinstance(result, Err):
        e = result.error
        return Err(
            ReleaseError(
                kind="repo_failed",
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
    return_head_sha: bool,
    head_sha_read_error: str | None = None,
    head_sha_invalid_error: str | None = None,
) -> Result[str | None, ReleaseError]:
    rels = [str(p.relative_to(repo_root)) for p in paths]
    console.print(f"git add -A -- {' '.join(rels)}", Style.DIM)
    console.print(f"git commit -m {message}", Style.DIM)
    console.print(f"git push -u origin {branch}", Style.DIM)

    if dry_run:
        if return_head_sha:
            return Ok("0" * 40)
        return Ok(None)

    add = run_git_command(cmd=["git", "add", "-A", "--", *rels], repo_root=repo_root)
    if isinstance(add, Err):
        e = add.error
        return Err(
            ReleaseError(
                kind="repo_failed",
                message="git add failed",
                hint=e.stderr.strip() or None,
            )
        )

    commit = run_git_command(cmd=["git", "commit", "-m", message], repo_root=repo_root)
    if isinstance(commit, Err):
        e = commit.error
        hint = e.stderr.strip() or None
        if hint is None:
            hint = "Configure git user.name/user.email, then retry."
        return Err(
            ReleaseError(
                kind="repo_failed",
                message="git commit failed",
                hint=hint,
            )
        )

    push = run_git_command(
        cmd=["git", "push", "-u", "origin", branch],
        repo_root=repo_root,
        network=True,
    )
    if isinstance(push, Err):
        e = push.error
        return Err(
            ReleaseError(
                kind="repo_failed",
                message="git push failed",
                hint=e.stderr.strip() or None,
            )
        )

    if not return_head_sha:
        return Ok(None)

    head = run_git_command(cmd=["git", "rev-parse", "HEAD"], repo_root=repo_root)
    if isinstance(head, Err):
        e = head.error
        return Err(
            ReleaseError(
                kind="repo_failed",
                message=head_sha_read_error or "failed to read branch head sha",
                hint=e.stderr.strip() or None,
            )
        )

    sha = head.value.strip()
    if len(sha) != 40:
        return Err(
            ReleaseError(
                kind="repo_failed",
                message=head_sha_invalid_error or "invalid branch head sha",
                hint=sha,
            )
        )

    return Ok(sha)
