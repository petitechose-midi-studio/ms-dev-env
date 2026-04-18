from __future__ import annotations

import json
import time
from pathlib import Path

from ms.core.result import Err, Ok, Result
from ms.core.structured import as_str_dict
from ms.release.errors import ReleaseError
from ms.release.infra.github.gh_base import run_gh_process
from ms.release.infra.github.timeouts import GH_TIMEOUT_SECONDS

_MERGEABLE_WAIT_SECONDS = 15 * 60
_MERGE_WAIT_SECONDS = 10 * 60
_POLL_SECONDS = 5


def _parse_view_payload(*, payload: str, pr_url: str) -> Result[dict[str, object], ReleaseError]:
    try:
        obj: object = json.loads(payload)
    except json.JSONDecodeError as e:
        return Err(
            ReleaseError(
                kind="repo_failed",
                message=f"invalid JSON from gh pr view: {e}",
                hint=pr_url,
            )
        )

    data = as_str_dict(obj)
    if data is None:
        return Err(
            ReleaseError(
                kind="repo_failed",
                message="unexpected gh pr view payload",
                hint=pr_url,
            )
        )
    return Ok(data)


def wait_until_mergeable(
    *,
    workspace_root: Path,
    repo_slug: str,
    pr_url: str,
    repo_label: str,
) -> Result[None, ReleaseError]:
    deadline = time.monotonic() + _MERGEABLE_WAIT_SECONDS
    while time.monotonic() < deadline:
        view = run_gh_process(
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
                    kind="repo_failed",
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
                    kind="repo_failed",
                    message=f"{repo_label} PR is {state.lower()} without merge",
                    hint=pr_url,
                )
            )
        if isinstance(merge_state, str) and merge_state == "CLEAN":
            return Ok(None)
        time.sleep(_POLL_SECONDS)

    return Err(
        ReleaseError(
            kind="repo_failed",
            message=f"timed out waiting for {repo_label} PR to become mergeable",
            hint=pr_url,
        )
    )


def wait_until_merged(
    *,
    workspace_root: Path,
    repo_slug: str,
    pr_url: str,
    repo_label: str,
) -> Result[None, ReleaseError]:
    deadline = time.monotonic() + _MERGE_WAIT_SECONDS
    while time.monotonic() < deadline:
        view = run_gh_process(
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
                    kind="repo_failed",
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
                    kind="repo_failed",
                    message=f"{repo_label} PR is {state.lower()} without merge",
                    hint=pr_url,
                )
            )
        time.sleep(_POLL_SECONDS)

    return Err(
        ReleaseError(
            kind="repo_failed",
            message=f"timed out waiting for {repo_label} PR merge",
            hint=pr_url,
        )
    )
