from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from ms.core.result import Err, Ok, Result
from ms.core.structured import as_obj_list, as_str_dict, get_int, get_str
from ms.output.console import ConsoleProtocol, Style
from ms.platform.process import run as run_process
from ms.services.release.config import DIST_DEFAULT_BRANCH, DIST_PUBLISH_WORKFLOW, DIST_REPO_SLUG
from ms.services.release.errors import ReleaseError
from ms.services.release.model import ReleaseChannel


@dataclass(frozen=True, slots=True)
class WorkflowRun:
    id: int
    url: str


def dispatch_publish_workflow(
    *,
    workspace_root: Path,
    channel: ReleaseChannel,
    tag: str,
    spec_path: str,
    console: ConsoleProtocol,
    dry_run: bool,
) -> Result[WorkflowRun, ReleaseError]:
    cmd = [
        "gh",
        "workflow",
        "run",
        DIST_PUBLISH_WORKFLOW,
        "--repo",
        DIST_REPO_SLUG,
        "--ref",
        DIST_DEFAULT_BRANCH,
        "-f",
        f"channel={channel}",
        "-f",
        f"tag={tag}",
        "-f",
        f"spec_path={spec_path}",
    ]

    console.print(" ".join(cmd[:3]) + " ...", Style.DIM)
    if dry_run:
        return Ok(WorkflowRun(id=0, url="(dry-run)"))

    result = run_process(cmd, cwd=workspace_root)
    if isinstance(result, Err):
        e = result.error
        return Err(
            ReleaseError(
                kind="workflow_failed",
                message="failed to dispatch publish workflow",
                hint=e.stderr.strip() or None,
            )
        )

    # Find the most recent run (best-effort).
    list_cmd = [
        "gh",
        "run",
        "list",
        "--repo",
        DIST_REPO_SLUG,
        "--workflow",
        DIST_PUBLISH_WORKFLOW,
        "--limit",
        "10",
        "--json",
        "databaseId,url,event,headBranch,createdAt",
    ]
    list_result = run_process(list_cmd, cwd=workspace_root)
    if isinstance(list_result, Err):
        e = list_result.error
        return Err(
            ReleaseError(
                kind="workflow_failed",
                message="failed to query workflow runs",
                hint=e.stderr.strip() or None,
            )
        )

    try:
        obj: object = json.loads(list_result.value)
    except json.JSONDecodeError as e:
        return Err(
            ReleaseError(
                kind="workflow_failed",
                message=f"invalid JSON from gh run list: {e}",
            )
        )

    raw = as_obj_list(obj)
    if raw is None:
        return Err(ReleaseError(kind="workflow_failed", message="unexpected gh run list payload"))

    for item in raw:
        d = as_str_dict(item)
        if d is None:
            continue

        event = get_str(d, "event")
        head = get_str(d, "headBranch")
        url = get_str(d, "url")
        run_id = get_int(d, "databaseId")
        if event != "workflow_dispatch":
            continue
        if head != DIST_DEFAULT_BRANCH:
            continue
        if url is None or run_id is None:
            continue
        return Ok(WorkflowRun(id=run_id, url=url))

    return Err(
        ReleaseError(
            kind="workflow_failed",
            message="could not find the dispatched workflow run",
            hint="Check Actions tab in the distribution repo.",
        )
    )


def watch_run(
    *,
    workspace_root: Path,
    run_id: int,
    console: ConsoleProtocol,
    dry_run: bool,
) -> Result[None, ReleaseError]:
    if run_id <= 0:
        return Ok(None)
    cmd = ["gh", "run", "watch", "--repo", DIST_REPO_SLUG, str(run_id), "--exit-status"]
    console.print(" ".join(cmd[:3]) + " ...", Style.DIM)
    if dry_run:
        return Ok(None)

    result = run_process(cmd, cwd=workspace_root)
    if isinstance(result, Err):
        e = result.error
        return Err(
            ReleaseError(
                kind="workflow_failed",
                message="workflow run failed",
                hint=e.stderr.strip() or None,
            )
        )
    return Ok(None)
