from __future__ import annotations

from pathlib import Path

from ms.core.result import Err, Ok, Result
from ms.output.console import ConsoleProtocol, Style
from ms.release.errors import ReleaseError
from ms.release.infra.github.gh_base import run_gh_process
from ms.release.infra.github.pr_state import wait_until_mergeable, wait_until_merged
from ms.release.infra.github.timeouts import GH_TIMEOUT_SECONDS


def _is_auto_merge_disabled(stderr: str | None) -> bool:
    if not stderr:
        return False
    return (
        "Auto merge is not allowed for this repository" in stderr
        or "enablePullRequestAutoMerge" in stderr
    )


def create_pull_request(
    *,
    workspace_root: Path,
    repo_slug: str,
    base_branch: str,
    branch: str,
    title: str,
    body: str,
    repo_label: str,
    console: ConsoleProtocol,
    dry_run: bool,
) -> Result[str, ReleaseError]:
    cmd = [
        "gh",
        "pr",
        "create",
        "--repo",
        repo_slug,
        "--base",
        base_branch,
        "--head",
        branch,
        "--title",
        title,
        "--body",
        body,
    ]

    console.print(" ".join(cmd[:3]) + " ...", Style.DIM)
    if dry_run:
        return Ok("(dry-run)")

    result = run_gh_process(cmd, cwd=workspace_root, timeout=GH_TIMEOUT_SECONDS)
    if isinstance(result, Err):
        e = result.error
        return Err(
            ReleaseError(
                kind="repo_failed",
                message=f"failed to create PR in {repo_label} repo",
                hint=e.stderr.strip() or None,
            )
        )

    url = result.value.strip()
    if not url.startswith("https://"):
        return Err(
            ReleaseError(
                kind="repo_failed",
                message="unexpected gh pr create output",
                hint=url,
            )
        )
    return Ok(url)


def merge_pull_request(
    *,
    workspace_root: Path,
    repo_slug: str,
    pr_url: str,
    repo_label: str,
    delete_branch: bool,
    allow_auto_merge_fallback: bool,
    console: ConsoleProtocol,
    dry_run: bool,
) -> Result[None, ReleaseError]:
    cmd = [
        "gh",
        "pr",
        "merge",
        pr_url,
        "--repo",
        repo_slug,
        "--rebase",
        "--auto",
    ]
    if delete_branch:
        cmd.append("--delete-branch")
    console.print(" ".join(cmd[:3]) + " ...", Style.DIM)
    if dry_run:
        return Ok(None)

    merged = run_gh_process(cmd, cwd=workspace_root, timeout=GH_TIMEOUT_SECONDS)
    if isinstance(merged, Err):
        e = merged.error
        if allow_auto_merge_fallback and _is_auto_merge_disabled(e.stderr):
            console.print(
                "auto-merge disabled for repo; falling back to direct merge after checks",
                Style.DIM,
            )

            mergeable = wait_until_mergeable(
                workspace_root=workspace_root,
                repo_slug=repo_slug,
                pr_url=pr_url,
                repo_label=repo_label,
            )
            if isinstance(mergeable, Err):
                return mergeable

            direct_cmd = [
                "gh",
                "pr",
                "merge",
                pr_url,
                "--repo",
                repo_slug,
                "--rebase",
                *(["--delete-branch"] if delete_branch else []),
            ]
            direct = run_gh_process(direct_cmd, cwd=workspace_root, timeout=GH_TIMEOUT_SECONDS)
            if isinstance(direct, Err):
                de = direct.error
                return Err(
                    ReleaseError(
                        kind="repo_failed",
                        message=f"failed to merge {repo_label} PR",
                        hint=de.stderr.strip() or pr_url,
                    )
                )
        else:
            return Err(
                ReleaseError(
                    kind="repo_failed",
                    message=f"failed to merge {repo_label} PR",
                    hint=e.stderr.strip() or pr_url,
                )
            )

    return wait_until_merged(
        workspace_root=workspace_root,
        repo_slug=repo_slug,
        pr_url=pr_url,
        repo_label=repo_label,
    )
