from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from pathlib import Path
from time import sleep
from uuid import uuid4

from ms.core.result import Err, Ok, Result
from ms.core.structured import as_obj_list, as_str_dict, get_int, get_str
from ms.output.console import ConsoleProtocol, Style
from ms.platform.process import run as run_process
from ms.services.release.config import (
    APP_CANDIDATE_WORKFLOW,
    APP_DEFAULT_BRANCH,
    APP_RELEASE_WORKFLOW,
    APP_REPO_SLUG,
    DIST_DEFAULT_BRANCH,
    DIST_PUBLISH_WORKFLOW,
    DIST_REPO_SLUG,
)
from ms.services.release.errors import ReleaseError
from ms.services.release.model import ReleaseChannel
from ms.services.release.timeouts import GH_TIMEOUT_SECONDS, GH_WATCH_TIMEOUT_SECONDS

_RUN_LOOKUP_MAX_ATTEMPTS = 6
_RUN_LOOKUP_DELAY_SECONDS = 1.0


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

    result = run_process(cmd, cwd=workspace_root, timeout=GH_TIMEOUT_SECONDS)
    if isinstance(result, Err):
        e = result.error
        return Err(
            ReleaseError(
                kind="workflow_failed",
                message="failed to dispatch workflow",
                hint=e.stderr.strip() or None,
            )
        )

    return _resolve_dispatched_run(
        workspace_root=workspace_root,
        repo_slug=repo_slug,
        workflow_file=workflow_file,
        ref=ref,
        request_id=request_id,
    )


def _resolve_dispatched_run(
    *,
    workspace_root: Path,
    repo_slug: str,
    workflow_file: str,
    ref: str,
    request_id: str,
) -> Result[WorkflowRun, ReleaseError]:
    list_cmd = [
        "gh",
        "run",
        "list",
        "--repo",
        repo_slug,
        "--workflow",
        workflow_file,
        "--limit",
        "20",
        "--json",
        "databaseId,url,event,headBranch,displayTitle",
    ]

    for attempt in range(_RUN_LOOKUP_MAX_ATTEMPTS):
        list_result = run_process(list_cmd, cwd=workspace_root, timeout=GH_TIMEOUT_SECONDS)
        if isinstance(list_result, Err):
            e = list_result.error
            return Err(
                ReleaseError(
                    kind="workflow_failed",
                    message="failed to query workflow runs",
                    hint=e.stderr.strip() or None,
                )
            )

        parsed = _find_dispatched_run(
            payload=list_result.value,
            ref=ref,
            request_id=request_id,
        )
        if isinstance(parsed, Err):
            return parsed
        if parsed.value is not None:
            return Ok(parsed.value)
        if attempt < _RUN_LOOKUP_MAX_ATTEMPTS - 1:
            sleep(_RUN_LOOKUP_DELAY_SECONDS)

    return Err(
        ReleaseError(
            kind="workflow_failed",
            message="could not deterministically identify the dispatched workflow run",
            hint=(
                f"Run list did not expose request_id={request_id}; check Actions in {repo_slug} "
                "and ensure workflow run title includes the dispatch request_id."
            ),
        )
    )


def _find_dispatched_run(
    *,
    payload: str,
    ref: str,
    request_id: str,
) -> Result[WorkflowRun | None, ReleaseError]:
    try:
        obj: object = json.loads(payload)
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
        title = get_str(d, "displayTitle")
        if event != "workflow_dispatch":
            continue
        if head != ref:
            continue
        if url is None or run_id is None:
            continue
        if not isinstance(title, str) or request_id not in title:
            continue
        return Ok(WorkflowRun(id=run_id, url=url, request_id=request_id))

    return Ok(None)


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
    source_sha: str,
    notes_markdown: str | None,
    notes_source_path: str | None,
    console: ConsoleProtocol,
    dry_run: bool,
) -> Result[WorkflowRun, ReleaseError]:
    inputs: tuple[tuple[str, str], ...]
    if notes_markdown is None:
        inputs = (("tag", tag), ("source_sha", source_sha))
    else:
        notes_b64 = base64.b64encode(notes_markdown.encode("utf-8")).decode("ascii")
        if len(notes_b64) > 60000:
            return Err(
                ReleaseError(
                    kind="invalid_input",
                    message="notes markdown is too large for workflow dispatch input",
                    hint="Use a shorter --notes-file (recommended < 45KB).",
                )
            )
        notes_source = (notes_source_path or "").strip()
        if len(notes_source) > 1024:
            notes_source = notes_source[:1021] + "..."

        console.print("app release input: notes_b64 attached", Style.DIM)
        if notes_source:
            console.print(f"app release input: notes_source={notes_source}", Style.DIM)

        inputs = (
            ("tag", tag),
            ("source_sha", source_sha),
            ("notes_b64", notes_b64),
            ("notes_source", notes_source),
        )

    return _dispatch_workflow(
        workspace_root=workspace_root,
        repo_slug=APP_REPO_SLUG,
        workflow_file=APP_RELEASE_WORKFLOW,
        ref=APP_DEFAULT_BRANCH,
        inputs=inputs,
        console=console,
        dry_run=dry_run,
    )


def dispatch_app_candidate_workflow(
    *,
    workspace_root: Path,
    source_sha: str,
    console: ConsoleProtocol,
    dry_run: bool,
) -> Result[WorkflowRun, ReleaseError]:
    return _dispatch_workflow(
        workspace_root=workspace_root,
        repo_slug=APP_REPO_SLUG,
        workflow_file=APP_CANDIDATE_WORKFLOW,
        ref=APP_DEFAULT_BRANCH,
        inputs=(("source_sha", source_sha),),
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

    result = run_process(cmd, cwd=workspace_root, timeout=GH_WATCH_TIMEOUT_SECONDS)
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
