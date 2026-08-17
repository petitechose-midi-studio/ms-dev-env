from __future__ import annotations

import base64
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from ms.core.result import Err, Ok, Result
from ms.output.console import ConsoleProtocol, Style
from ms.release.domain.config import (
    APP_CANDIDATE_WORKFLOW,
    APP_DEFAULT_BRANCH,
    APP_RELEASE_WORKFLOW,
    APP_REPO_SLUG,
    CORE_DEFAULT_BRANCH,
    CORE_REPO_SLUG,
    DIST_DEFAULT_BRANCH,
    DIST_PUBLISH_WORKFLOW,
    DIST_REPO_SLUG,
    MS_DEFAULT_BRANCH,
    MS_RELEASE_ALIGNMENT_WORKFLOW,
    MS_REPO_SLUG,
)
from ms.release.domain.models import ReleaseChannel
from ms.release.errors import ReleaseError
from ms.release.infra.github.client import get_ref_head_sha

from .gh_base import run_gh_process
from .timeouts import GH_TIMEOUT_SECONDS
from .workflow_dispatch_lookup import find_dispatched_run, resolve_dispatched_run


@dataclass(frozen=True, slots=True)
class WorkflowRun:
    id: int
    url: str
    request_id: str


def _dispatch_request_id(
    *,
    repo_slug: str,
    workflow_file: str,
    ref: str,
    inputs: tuple[tuple[str, str], ...],
    identity: tuple[tuple[str, str], ...] = (),
) -> str:
    payload = json.dumps(
        (repo_slug, workflow_file, ref, inputs, identity),
        separators=(",", ":"),
    ).encode("utf-8")
    return f"ms-{hashlib.sha256(payload).hexdigest()[:20]}"


def _dispatch_workflow(
    *,
    workspace_root: Path,
    repo_slug: str,
    workflow_file: str,
    ref: str,
    inputs: tuple[tuple[str, str], ...],
    identity: tuple[tuple[str, str], ...] = (),
    console: ConsoleProtocol,
    dry_run: bool,
) -> Result[WorkflowRun, ReleaseError]:
    resolved_ref = ref
    if not dry_run:
        head = get_ref_head_sha(workspace_root=workspace_root, repo=repo_slug, ref=ref)
        if isinstance(head, Err):
            return head
        resolved_ref = head.value

    request_id = _dispatch_request_id(
        repo_slug=repo_slug,
        workflow_file=workflow_file,
        ref=resolved_ref,
        inputs=inputs,
        identity=identity,
    )
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
    for key, value in inputs:
        cmd.extend(["-f", f"{key}={value}"])
    cmd.extend(["-f", f"request_id={request_id}"])

    console.print(" ".join(cmd[:3]) + " ...", Style.DIM)
    console.print(f"dispatch request_id: {request_id}", Style.DIM)
    if dry_run:
        return Ok(WorkflowRun(id=0, url="(dry-run)", request_id=request_id))

    existing = find_dispatched_run(
        workspace_root=workspace_root,
        repo_slug=repo_slug,
        request_id=request_id,
    )
    if isinstance(existing, Err):
        return existing
    if existing.value is not None:
        console.print(f"reusing workflow run: {existing.value.url}", Style.DIM)
        return Ok(
            WorkflowRun(
                id=existing.value.run_id,
                url=existing.value.url,
                request_id=request_id,
            )
        )

    result = run_gh_process(cmd, cwd=workspace_root, timeout=GH_TIMEOUT_SECONDS)
    if isinstance(result, Err):
        error = result.error
        return Err(
            ReleaseError(
                kind="workflow_failed",
                message="failed to dispatch workflow",
                hint=error.stderr.strip() or None,
            )
        )

    resolved = resolve_dispatched_run(
        workspace_root=workspace_root,
        repo_slug=repo_slug,
        request_id=request_id,
    )
    if isinstance(resolved, Err):
        return resolved

    return Ok(
        WorkflowRun(
            id=resolved.value.run_id,
            url=resolved.value.url,
            request_id=request_id,
        )
    )


def dispatch_publish_workflow(
    *,
    workspace_root: Path,
    channel: ReleaseChannel,
    tag: str,
    spec_path: str,
    tooling_sha: str,
    console: ConsoleProtocol,
    dry_run: bool,
) -> Result[WorkflowRun, ReleaseError]:
    return _dispatch_workflow(
        workspace_root=workspace_root,
        repo_slug=DIST_REPO_SLUG,
        workflow_file=DIST_PUBLISH_WORKFLOW,
        ref=DIST_DEFAULT_BRANCH,
        inputs=(
            ("channel", channel),
            ("tag", tag),
            ("spec_path", spec_path),
            ("tooling_sha", tooling_sha),
        ),
        console=console,
        dry_run=dry_run,
    )


def dispatch_candidate_workflow(
    *,
    workspace_root: Path,
    repo_slug: str,
    workflow_file: str,
    ref: str,
    inputs: tuple[tuple[str, str], ...],
    console: ConsoleProtocol,
    dry_run: bool,
) -> Result[WorkflowRun, ReleaseError]:
    return _dispatch_workflow(
        workspace_root=workspace_root,
        repo_slug=repo_slug,
        workflow_file=workflow_file,
        ref=ref,
        inputs=inputs,
        console=console,
        dry_run=dry_run,
    )


def dispatch_app_release_workflow(
    *,
    workspace_root: Path,
    tag: str,
    source_sha: str,
    tooling_sha: str,
    notes_markdown: str | None,
    notes_source_path: str | None,
    console: ConsoleProtocol,
    dry_run: bool,
) -> Result[WorkflowRun, ReleaseError]:
    inputs: tuple[tuple[str, str], ...]
    if notes_markdown is None:
        inputs = (("tag", tag), ("source_sha", source_sha), ("tooling_sha", tooling_sha))
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
            ("tooling_sha", tooling_sha),
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
    tooling_sha: str,
    console: ConsoleProtocol,
    dry_run: bool,
) -> Result[WorkflowRun, ReleaseError]:
    return _dispatch_workflow(
        workspace_root=workspace_root,
        repo_slug=APP_REPO_SLUG,
        workflow_file=APP_CANDIDATE_WORKFLOW,
        ref=APP_DEFAULT_BRANCH,
        inputs=(("source_sha", source_sha), ("tooling_sha", tooling_sha)),
        console=console,
        dry_run=dry_run,
    )


def dispatch_release_alignment_workflow(
    *,
    workspace_root: Path,
    build_wasm: bool,
    core_sha: str | None = None,
    console: ConsoleProtocol,
    dry_run: bool,
) -> Result[WorkflowRun, ReleaseError]:
    if core_sha is None and not dry_run:
        head = get_ref_head_sha(
            workspace_root=workspace_root,
            repo=CORE_REPO_SLUG,
            ref=CORE_DEFAULT_BRANCH,
        )
        if isinstance(head, Err):
            return head
        core_sha = head.value

    return _dispatch_workflow(
        workspace_root=workspace_root,
        repo_slug=MS_REPO_SLUG,
        workflow_file=MS_RELEASE_ALIGNMENT_WORKFLOW,
        ref=MS_DEFAULT_BRANCH,
        inputs=(("build_wasm", "true" if build_wasm else "false"),),
        identity=(("core_sha", core_sha or "dry-run"),),
        console=console,
        dry_run=dry_run,
    )
