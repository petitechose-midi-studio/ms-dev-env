from __future__ import annotations

import json
import time
from pathlib import Path

from ms.core.result import Err, Ok, Result
from ms.core.structured import as_str_dict
from ms.output.console import ConsoleProtocol, Style
from ms.platform.process import run as run_process
from ms.services.release.errors import ReleaseError
from ms.services.release.timeouts import GH_TIMEOUT_SECONDS

_MERGEABLE_WAIT_SECONDS = 15 * 60
_MERGE_WAIT_SECONDS = 10 * 60
_POLL_SECONDS = 5


def _is_auto_merge_disabled(stderr: str | None) -> bool:
    if not stderr:
        return False
    return (
        "Auto merge is not allowed for this repository" in stderr
        or "enablePullRequestAutoMerge" in stderr
    )


def _parse_view_payload(*, payload: str, pr_url: str) -> Result[dict[str, object], ReleaseError]:
    try:
        obj: object = json.loads(payload)
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
    return Ok(data)


def _wait_until_mergeable(
    *,
    workspace_root: Path,
    repo_slug: str,
    pr_url: str,
    repo_label: str,
) -> Result[None, ReleaseError]:
    deadline = time.monotonic() + _MERGEABLE_WAIT_SECONDS
    while time.monotonic() < deadline:
        view = run_process(
            [
                "gh",
                "pr",
                "view",
                pr_url,
                "--repo",
                repo_slug,
                "--json",
                "state,mergeStateStatus",
            ],
            cwd=workspace_root,
            timeout=GH_TIMEOUT_SECONDS,
        )
        if isinstance(view, Err):
            e = view.error
            return Err(
                ReleaseError(
                    kind="dist_repo_failed",
                    message=f"failed to query {repo_label} PR merge status",
                    hint=e.stderr.strip() or pr_url,
                )
            )

        parsed = _parse_view_payload(payload=view.value, pr_url=pr_url)
        if isinstance(parsed, Err):
            return parsed

        state = parsed.value.get("state")
        merge_state = parsed.value.get("mergeStateStatus")
        if isinstance(state, str) and state != "OPEN":
            return Err(
                ReleaseError(
                    kind="dist_repo_failed",
                    message=f"{repo_label} PR is {state.lower()} without merge",
                    hint=pr_url,
                )
            )
        if isinstance(merge_state, str) and merge_state == "CLEAN":
            return Ok(None)
        time.sleep(_POLL_SECONDS)

    return Err(
        ReleaseError(
            kind="dist_repo_failed",
            message=f"timed out waiting for {repo_label} PR to become mergeable",
            hint=pr_url,
        )
    )


def _wait_until_merged(
    *,
    workspace_root: Path,
    repo_slug: str,
    pr_url: str,
    repo_label: str,
) -> Result[None, ReleaseError]:
    deadline = time.monotonic() + _MERGE_WAIT_SECONDS
    while time.monotonic() < deadline:
        view = run_process(
            [
                "gh",
                "pr",
                "view",
                pr_url,
                "--repo",
                repo_slug,
                "--json",
                "state,mergedAt",
            ],
            cwd=workspace_root,
            timeout=GH_TIMEOUT_SECONDS,
        )
        if isinstance(view, Err):
            e = view.error
            return Err(
                ReleaseError(
                    kind="dist_repo_failed",
                    message=f"failed to query {repo_label} PR state",
                    hint=e.stderr.strip() or pr_url,
                )
            )

        parsed = _parse_view_payload(payload=view.value, pr_url=pr_url)
        if isinstance(parsed, Err):
            return parsed

        state = parsed.value.get("state")
        merged_at = parsed.value.get("mergedAt")
        merged = (isinstance(state, str) and state == "MERGED") or (
            isinstance(merged_at, str) and merged_at.strip() != ""
        )
        if merged:
            return Ok(None)

        if isinstance(state, str) and state != "OPEN":
            return Err(
                ReleaseError(
                    kind="dist_repo_failed",
                    message=f"{repo_label} PR is {state.lower()} without merge",
                    hint=pr_url,
                )
            )
        time.sleep(_POLL_SECONDS)

    return Err(
        ReleaseError(
            kind="dist_repo_failed",
            message=f"timed out waiting for {repo_label} PR merge",
            hint=pr_url,
        )
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

    result = run_process(cmd, cwd=workspace_root, timeout=GH_TIMEOUT_SECONDS)
    if isinstance(result, Err):
        e = result.error
        return Err(
            ReleaseError(
                kind="dist_repo_failed",
                message=f"failed to create PR in {repo_label} repo",
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

    merged = run_process(cmd, cwd=workspace_root, timeout=GH_TIMEOUT_SECONDS)
    if isinstance(merged, Err):
        e = merged.error
        if allow_auto_merge_fallback and _is_auto_merge_disabled(e.stderr):
            console.print(
                "auto-merge disabled for repo; falling back to direct merge after checks",
                Style.DIM,
            )

            mergeable = _wait_until_mergeable(
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
            direct = run_process(direct_cmd, cwd=workspace_root, timeout=GH_TIMEOUT_SECONDS)
            if isinstance(direct, Err):
                de = direct.error
                return Err(
                    ReleaseError(
                        kind="dist_repo_failed",
                        message=f"failed to merge {repo_label} PR",
                        hint=de.stderr.strip() or pr_url,
                    )
                )
        else:
            return Err(
                ReleaseError(
                    kind="dist_repo_failed",
                    message=f"failed to merge {repo_label} PR",
                    hint=e.stderr.strip() or pr_url,
                )
            )

    return _wait_until_merged(
        workspace_root=workspace_root,
        repo_slug=repo_slug,
        pr_url=pr_url,
        repo_label=repo_label,
    )
