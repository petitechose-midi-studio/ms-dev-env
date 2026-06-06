from __future__ import annotations

import json
from pathlib import Path

from ms.core.result import Err, Ok, Result
from ms.core.structured import as_str_dict
from ms.output.console import ConsoleProtocol, Style
from ms.release.errors import ReleaseError
from ms.release.infra.github.app_auth import release_app_token_for_repo
from ms.release.infra.github.gh_base import run_gh_process
from ms.release.infra.github.pr_review import approve_pull_request_if_required
from ms.release.infra.github.pr_state import wait_until_merged
from ms.release.infra.github.timeouts import GH_TIMEOUT_SECONDS


def _is_auto_merge_disabled(stderr: str | None) -> bool:
    if not stderr:
        return False
    return (
        "Auto merge is not allowed for this repository" in stderr
        or "enablePullRequestAutoMerge" in stderr
    )


def _is_already_merged(stderr: str | None) -> bool:
    return "already merged" in stderr.lower() if stderr else False


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
    if dry_run:
        console.print("gh pr create ...", Style.DIM)
        return Ok("(dry-run)")

    token = release_app_token_for_repo(workspace_root=workspace_root, repo_slug=repo_slug)
    if isinstance(token, Err):
        return token
    if token.value is not None:
        return _create_pull_request_with_release_app(
            workspace_root=workspace_root,
            repo_slug=repo_slug,
            base_branch=base_branch,
            branch=branch,
            title=title,
            body=body,
            repo_label=repo_label,
            console=console,
            token=token.value,
        )

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


def _create_pull_request_with_release_app(
    *,
    workspace_root: Path,
    repo_slug: str,
    base_branch: str,
    branch: str,
    title: str,
    body: str,
    repo_label: str,
    console: ConsoleProtocol,
    token: str,
) -> Result[str, ReleaseError]:
    cmd = [
        "gh",
        "api",
        "--method",
        "POST",
        f"/repos/{repo_slug}/pulls",
        "-f",
        f"title={title}",
        "-f",
        f"head={branch}",
        "-f",
        f"base={base_branch}",
        "-f",
        f"body={body}",
    ]
    console.print("gh api ... (release app PR)", Style.DIM)

    result = run_gh_process(
        cmd,
        cwd=workspace_root,
        timeout=GH_TIMEOUT_SECONDS,
        env={"GH_TOKEN": token},
    )
    if isinstance(result, Err):
        e = result.error
        return Err(
            ReleaseError(
                kind="repo_failed",
                message=f"failed to create PR in {repo_label} repo with release GitHub App",
                hint=e.stderr.strip() or None,
            )
        )

    try:
        obj: object = json.loads(result.value)
    except json.JSONDecodeError as e:
        return Err(
            ReleaseError(
                kind="repo_failed",
                message="unexpected gh api PR create output",
                hint=str(e),
            )
        )

    data = as_str_dict(obj)
    url = data.get("html_url") if data is not None else None
    if not isinstance(url, str) or not url.startswith("https://"):
        return Err(
            ReleaseError(
                kind="repo_failed",
                message="unexpected gh api PR create payload",
                hint=result.value.strip(),
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
    console: ConsoleProtocol,
    dry_run: bool,
) -> Result[None, ReleaseError]:
    approved = approve_pull_request_if_required(
        workspace_root=workspace_root,
        repo_slug=repo_slug,
        pr_url=pr_url,
        repo_label=repo_label,
        console=console,
        dry_run=dry_run,
    )
    if isinstance(approved, Err):
        return approved

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
        if _is_already_merged(e.stderr):
            console.print("PR already merged; verifying final state", Style.DIM)
            return wait_until_merged(
                workspace_root=workspace_root,
                repo_slug=repo_slug,
                pr_url=pr_url,
                repo_label=repo_label,
            )
        if _is_auto_merge_disabled(e.stderr):
            return Err(
                ReleaseError(
                    kind="repo_failed",
                    message=f"auto-merge is disabled for {repo_label} repo",
                    hint=(
                        f"Enable Allow auto-merge for {repo_slug}, then rerun. PR: {pr_url}"
                    ),
                )
            )
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
