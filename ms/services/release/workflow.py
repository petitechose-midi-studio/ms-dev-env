from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from ms.core.result import Err, Ok, Result
from ms.core.structured import as_obj_list, as_str_dict, get_int, get_str
from ms.output.console import ConsoleProtocol, Style
from ms.platform.process import run as run_process
from ms.services.release.config import (
    APP_DEFAULT_BRANCH,
    APP_RELEASE_WORKFLOW,
    APP_REPO_SLUG,
    DIST_DEFAULT_BRANCH,
    DIST_PUBLISH_WORKFLOW,
    DIST_REPO_SLUG,
)
from ms.services.release.errors import ReleaseError
from ms.services.release.model import ReleaseChannel


@dataclass(frozen=True, slots=True)
class WorkflowRun:
    id: int
    url: str
    request_id: str


def _dispatch_workflow(
    *,
    workspace_root: Path,
    repo_slug: str,
    workflow_file: str,
    ref: str,
    inputs: tuple[tuple[str, str], ...],
    console: ConsoleProtocol,
    dry_run: bool,
) -> Result[WorkflowRun, ReleaseError]:
    request_id = f"ms-{uuid4().hex[:12]}"
    cmd = [
        "gh",
        "workflow",
        "run",
        workflow_file,
        "--repo",
        repo_slug,
        "--ref",
        ref,
    ]
    for k, v in inputs:
        cmd.extend(["-f", f"{k}={v}"])
    cmd.extend(["-f", f"request_id={request_id}"])

    console.print(" ".join(cmd[:3]) + " ...", Style.DIM)
    console.print(f"dispatch request_id: {request_id}", Style.DIM)
    if dry_run:
        return Ok(WorkflowRun(id=0, url="(dry-run)", request_id=request_id))

    result = run_process(cmd, cwd=workspace_root)
    if isinstance(result, Err):
        e = result.error
        return Err(
            ReleaseError(
                kind="workflow_failed",
                message="failed to dispatch workflow",
                hint=e.stderr.strip() or None,
            )
        )

    list_cmd = [
        "gh",
        "run",
        "list",
        "--repo",
        repo_slug,
        "--workflow",
        workflow_file,
        "--limit",
        "10",
        "--json",
        "databaseId,url,event,headBranch,createdAt,displayTitle",
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

    fallback: WorkflowRun | None = None

    for item in raw:
        d = as_str_dict(item)
        if d is None:
            continue

        event = get_str(d, "event")
        head = get_str(d, "headBranch")
        url = get_str(d, "url")
        run_id = get_int(d, "databaseId")
        title = get_str(d, "displayTitle")
        if event != "workflow_dispatch":
            continue
        if head != ref:
            continue
        if url is None or run_id is None:
            continue

        run = WorkflowRun(id=run_id, url=url, request_id=request_id)
        if fallback is None:
            fallback = run

        if isinstance(title, str) and request_id in title:
            return Ok(run)

    if fallback is not None:
        return Ok(fallback)

    return Err(
        ReleaseError(
            kind="workflow_failed",
            message="could not find the dispatched workflow run",
            hint=f"Check Actions tab in {repo_slug}.",
        )
    )


def dispatch_publish_workflow(
    *,
    workspace_root: Path,
    channel: ReleaseChannel,
    tag: str,
    spec_path: str,
    console: ConsoleProtocol,
    dry_run: bool,
) -> Result[WorkflowRun, ReleaseError]:
    return _dispatch_workflow(
        workspace_root=workspace_root,
        repo_slug=DIST_REPO_SLUG,
        workflow_file=DIST_PUBLISH_WORKFLOW,
        ref=DIST_DEFAULT_BRANCH,
        inputs=(("channel", channel), ("tag", tag), ("spec_path", spec_path)),
        console=console,
        dry_run=dry_run,
    )


def dispatch_app_release_workflow(
    *,
    workspace_root: Path,
    tag: str,
    console: ConsoleProtocol,
    dry_run: bool,
) -> Result[WorkflowRun, ReleaseError]:
    return _dispatch_workflow(
        workspace_root=workspace_root,
        repo_slug=APP_REPO_SLUG,
        workflow_file=APP_RELEASE_WORKFLOW,
        ref=APP_DEFAULT_BRANCH,
        inputs=(("tag", tag),),
        console=console,
        dry_run=dry_run,
    )


def watch_run(
    *,
    workspace_root: Path,
    run_id: int,
    repo_slug: str,
    console: ConsoleProtocol,
    dry_run: bool,
) -> Result[None, ReleaseError]:
    if run_id <= 0:
        return Ok(None)
    cmd = ["gh", "run", "watch", "--repo", repo_slug, str(run_id), "--exit-status"]
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
