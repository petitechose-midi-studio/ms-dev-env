from __future__ import annotations

import json
from pathlib import Path

from ms.core.result import Err, Ok, Result
from ms.core.structured import as_str_dict
from ms.output.console import ConsoleProtocol, Style
from ms.release.errors import ReleaseError
from ms.release.infra.github.gh_base import run_gh_process
from ms.release.infra.github.timeouts import GH_TIMEOUT_SECONDS


def _is_self_approval_error(stderr: str | None) -> bool:
    if not stderr:
        return False
    text = stderr.lower()
    return (
        "can't approve your own pull request" in text
        or "cannot approve your own pull request" in text
        or "can not approve your own pull request" in text
    )


def approve_pull_request_if_required(
    *,
    workspace_root: Path,
    repo_slug: str,
    pr_url: str,
    repo_label: str,
    console: ConsoleProtocol,
    dry_run: bool,
) -> Result[None, ReleaseError]:
    console.print("Checking release PR review state", Style.DIM)
    if dry_run:
        return Ok(None)

    view = run_gh_process(
        [
            "gh",
            "pr",
            "view",
            pr_url,
            "--repo",
            repo_slug,
            "--json",
            "reviewDecision",
        ],
        cwd=workspace_root,
        timeout=GH_TIMEOUT_SECONDS,
    )
    if isinstance(view, Err):
        e = view.error
        return Err(
            ReleaseError(
                kind="repo_failed",
                message=f"failed to query {repo_label} PR review state",
                hint=e.stderr.strip() or pr_url,
            )
        )

    try:
        obj: object = json.loads(view.value)
    except json.JSONDecodeError as e:
        return Err(
            ReleaseError(
                kind="repo_failed",
                message=f"invalid JSON from gh pr view: {e}",
                hint=pr_url,
            )
        )

    data = as_str_dict(obj)
    review_decision = data.get("reviewDecision") if data is not None else None
    if review_decision != "REVIEW_REQUIRED":
        return Ok(None)

    cmd = [
        "gh",
        "pr",
        "review",
        pr_url,
        "--repo",
        repo_slug,
        "--approve",
        "--body",
        "Approved by ms release after local release preflight.",
    ]
    console.print("gh pr review ...", Style.DIM)
    approved = run_gh_process(cmd, cwd=workspace_root, timeout=GH_TIMEOUT_SECONDS)
    if isinstance(approved, Err):
        e = approved.error
        if _is_self_approval_error(e.stderr):
            return Err(
                ReleaseError(
                    kind="repo_failed",
                    message=(
                        f"{repo_label} PR requires approval from a different GitHub identity"
                    ),
                    hint=(
                        "Configure the release GitHub App so the PR is authored by the app, "
                        f"then approve with the maintainer account. PR: {pr_url}"
                    ),
                )
            )
        return Err(
            ReleaseError(
                kind="repo_failed",
                message=f"failed to approve {repo_label} PR",
                hint=e.stderr.strip() or pr_url,
            )
        )

    return Ok(None)
