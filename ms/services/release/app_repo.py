from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path

from ms.core.result import Err, Ok, Result
from ms.core.structured import as_str_dict
from ms.output.console import ConsoleProtocol, Style
from ms.platform.process import run as run_process
from ms.services.release.config import APP_DEFAULT_BRANCH, APP_LOCAL_DIR, APP_REPO_SLUG
from ms.services.release.errors import ReleaseError


@dataclass(frozen=True, slots=True)
class AppRepoPaths:
    root: Path


def ensure_app_repo(
    *,
    workspace_root: Path,
    console: ConsoleProtocol,
    dry_run: bool,
) -> Result[AppRepoPaths, ReleaseError]:
    repo_root = workspace_root / APP_LOCAL_DIR
    if repo_root.is_dir() and (repo_root / ".git").is_dir():
        return Ok(AppRepoPaths(root=repo_root))

    console.print(f"clone {APP_REPO_SLUG} -> {repo_root}", Style.DIM)
    if dry_run:
        return Ok(AppRepoPaths(root=repo_root))

    repo_root.parent.mkdir(parents=True, exist_ok=True)
    result = run_process(["gh", "repo", "clone", APP_REPO_SLUG, str(repo_root)], cwd=workspace_root)
    if isinstance(result, Err):
        e = result.error
        return Err(
            ReleaseError(
                kind="dist_repo_failed",
                message="failed to clone app repo",
                hint=e.stderr.strip() or None,
            )
        )

    return Ok(AppRepoPaths(root=repo_root))


def ensure_clean_git_repo(*, repo_root: Path) -> Result[None, ReleaseError]:
    result = run_process(["git", "status", "--porcelain"], cwd=repo_root)
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
                message=f"app repo is dirty: {repo_root}",
                hint="Commit/stash changes in ms-manager/ then retry.",
            )
        )

    return Ok(None)


def checkout_main_and_pull(
    *,
    repo_root: Path,
    console: ConsoleProtocol,
    dry_run: bool,
) -> Result[None, ReleaseError]:
    console.print(f"git checkout {APP_DEFAULT_BRANCH}", Style.DIM)
    console.print("git pull --ff-only", Style.DIM)
    if dry_run:
        return Ok(None)

    for cmd in (
        ["git", "checkout", APP_DEFAULT_BRANCH],
        ["git", "pull", "--ff-only", "origin", APP_DEFAULT_BRANCH],
    ):
        result = run_process(cmd, cwd=repo_root)
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

    result = run_process(["git", "checkout", "-b", branch], cwd=repo_root)
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

    add = run_process(["git", "add", "-A", "--", *rels], cwd=repo_root)
    if isinstance(add, Err):
        e = add.error
        return Err(
            ReleaseError(
                kind="dist_repo_failed",
                message="git add failed",
                hint=e.stderr.strip() or None,
            )
        )

    commit = run_process(["git", "commit", "-m", message], cwd=repo_root)
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

    push = run_process(["git", "push", "-u", "origin", branch], cwd=repo_root)
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
    cmd = [
        "gh",
        "pr",
        "create",
        "--repo",
        APP_REPO_SLUG,
        "--base",
        APP_DEFAULT_BRANCH,
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

    result = run_process(cmd, cwd=workspace_root)
    if isinstance(result, Err):
        e = result.error
        return Err(
            ReleaseError(
                kind="dist_repo_failed",
                message="failed to create PR in app repo",
                hint=e.stderr.strip() or None,
            )
        )

    url = result.value.strip()
    if not url.startswith("https://"):
        return Err(
            ReleaseError(
                kind="dist_repo_failed",
                message="unexpected gh pr create output",
                hint=url,
            )
        )
    return Ok(url)


def merge_pr(
    *,
    workspace_root: Path,
    pr_url: str,
    console: ConsoleProtocol,
    dry_run: bool,
) -> Result[None, ReleaseError]:
    def _is_auto_merge_disabled(stderr: str | None) -> bool:
        if not stderr:
            return False
        return (
            "Auto merge is not allowed for this repository" in stderr
            or "enablePullRequestAutoMerge" in stderr
        )

    cmd = [
        "gh",
        "pr",
        "merge",
        pr_url,
        "--repo",
        APP_REPO_SLUG,
        "--rebase",
        "--delete-branch",
        "--auto",
    ]
    console.print(" ".join(cmd[:3]) + " ...", Style.DIM)
    if dry_run:
        return Ok(None)

    result = run_process(cmd, cwd=workspace_root)
    if isinstance(result, Err):
        e = result.error
        if _is_auto_merge_disabled(e.stderr):
            console.print(
                "auto-merge disabled for repo; falling back to direct merge after checks",
                Style.DIM,
            )

            deadline = time.monotonic() + 15 * 60
            while time.monotonic() < deadline:
                view = run_process(
                    [
                        "gh",
                        "pr",
                        "view",
                        pr_url,
                        "--repo",
                        APP_REPO_SLUG,
                        "--json",
                        "state,mergeStateStatus",
                    ],
                    cwd=workspace_root,
                )
                if isinstance(view, Err):
                    ve = view.error
                    return Err(
                        ReleaseError(
                            kind="dist_repo_failed",
                            message="failed to query app PR merge status",
                            hint=ve.stderr.strip() or pr_url,
                        )
                    )

                try:
                    obj: object = json.loads(view.value)
                except json.JSONDecodeError as je:
                    return Err(
                        ReleaseError(
                            kind="dist_repo_failed",
                            message=f"invalid JSON from gh pr view: {je}",
                            hint=pr_url,
                        )
                    )

                data = as_str_dict(obj)
                if data is None:
                    return Err(
                        ReleaseError(
                            kind="dist_repo_failed",
                            message="unexpected gh pr view payload",
                            hint=pr_url,
                        )
                    )

                state = data.get("state")
                merge_state = data.get("mergeStateStatus")
                if isinstance(state, str) and state != "OPEN":
                    return Err(
                        ReleaseError(
                            kind="dist_repo_failed",
                            message=f"app PR is {state.lower()} without merge",
                            hint=pr_url,
                        )
                    )
                if isinstance(merge_state, str) and merge_state == "CLEAN":
                    break
                time.sleep(5)
            else:
                return Err(
                    ReleaseError(
                        kind="dist_repo_failed",
                        message="timed out waiting for app PR to become mergeable",
                        hint=pr_url,
                    )
                )

            direct = run_process(
                [
                    "gh",
                    "pr",
                    "merge",
                    pr_url,
                    "--repo",
                    APP_REPO_SLUG,
                    "--rebase",
                    "--delete-branch",
                ],
                cwd=workspace_root,
            )
            if isinstance(direct, Err):
                de = direct.error
                return Err(
                    ReleaseError(
                        kind="dist_repo_failed",
                        message="failed to merge app PR",
                        hint=de.stderr.strip() or pr_url,
                    )
                )
        else:
            return Err(
                ReleaseError(
                    kind="dist_repo_failed",
                    message="failed to merge app PR",
                    hint=e.stderr.strip() or pr_url,
                )
            )

    deadline = time.monotonic() + 10 * 60
    while time.monotonic() < deadline:
        view = run_process(
            [
                "gh",
                "pr",
                "view",
                pr_url,
                "--repo",
                APP_REPO_SLUG,
                "--json",
                "state,mergedAt",
            ],
            cwd=workspace_root,
        )
        if isinstance(view, Err):
            e = view.error
            return Err(
                ReleaseError(
                    kind="dist_repo_failed",
                    message="failed to query app PR state",
                    hint=e.stderr.strip() or pr_url,
                )
            )

        try:
            obj: object = json.loads(view.value)
        except json.JSONDecodeError as e:
            return Err(
                ReleaseError(
                    kind="dist_repo_failed",
                    message=f"invalid JSON from gh pr view: {e}",
                    hint=pr_url,
                )
            )

        data = as_str_dict(obj)
        if data is None:
            return Err(
                ReleaseError(
                    kind="dist_repo_failed",
                    message="unexpected gh pr view payload",
                    hint=pr_url,
                )
            )

        state = data.get("state")
        merged_at = data.get("mergedAt")

        merged = (isinstance(state, str) and state == "MERGED") or (
            isinstance(merged_at, str) and merged_at.strip() != ""
        )
        if merged:
            return Ok(None)

        if isinstance(state, str) and state != "OPEN":
            return Err(
                ReleaseError(
                    kind="dist_repo_failed",
                    message=f"app PR is {state.lower()} without merge",
                    hint=pr_url,
                )
            )

        time.sleep(5)

    return Err(
        ReleaseError(
            kind="dist_repo_failed",
            message="timed out waiting for app PR merge",
            hint=pr_url,
        )
    )
