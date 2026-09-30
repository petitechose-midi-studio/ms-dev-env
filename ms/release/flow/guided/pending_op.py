"""Reconciliation of a release operation persisted before dispatch.

A pending operation is written to the session before the remote dispatch.
On resume, we never replay blindly and we never declare success from the mere
existence of a release: completion requires a proven dispatch identity
(``request_id`` marker + matching run). Anything else stays undetermined.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from time import sleep
from typing import Literal

from ms.core.result import Err, Ok, Result
from ms.core.structured import as_str_dict, get_str
from ms.release.errors import ReleaseError
from ms.release.infra.github.gh_base import gh_api_json
from ms.release.infra.github.releases import release_exists_by_tag
from ms.release.infra.github.workflow_dispatch_lookup import find_dispatched_run
from ms.release.infra.github.workflows import dispatch_request_id

PendingState = Literal["completed", "in_flight", "failed", "undetermined"]

_MARKER_ATTEMPTS = 6
_MARKER_DELAY_SECONDS = 5.0


@dataclass(frozen=True, slots=True)
class PendingReconciliation:
    state: PendingState
    detail: str
    run_url: str | None = None


def reconcile_pending_op(
    *,
    workspace_root: Path,
    repo: str,
    workflow_file: str,
    tag: str,
    request_id: str | None,
    source_sha: str | None = None,
    tooling_sha: str | None = None,
    inputs: tuple[tuple[str, str], ...] = (),
    attempts: int = _MARKER_ATTEMPTS,
    delay_seconds: float = _MARKER_DELAY_SECONDS,
) -> Result[PendingReconciliation, ReleaseError]:
    """Classify a previously dispatched operation without replaying it.

    ``completed`` requires the persisted ``request_id`` to resolve to a real
    run that succeeded, plus the expected release. A release with an
    unverified dispatch identity is reported as ``undetermined``.
    """
    if request_id:
        run = _find_marker_run(
            workspace_root=workspace_root,
            repo=repo,
            request_id=request_id,
            attempts=attempts,
            delay_seconds=delay_seconds,
        )
        if isinstance(run, Err):
            return run
        if run.value is not None:
            classified = _classify_run(
                workspace_root=workspace_root,
                repo=repo,
                workflow_file=workflow_file,
                run_id=run.value.run_id,
                run_url=run.value.url,
                tag=tag,
                source_sha=source_sha,
                tooling_sha=tooling_sha,
                request_id=request_id,
                inputs=inputs,
            )
            if isinstance(classified, Err):
                return classified
            return Ok(classified.value)

    released = release_exists_by_tag(workspace_root=workspace_root, repo=repo, tag=tag)
    if isinstance(released, Err):
        return released
    if released.value:
        return Ok(
            PendingReconciliation(
                state="undetermined",
                detail=(
                    f"release {tag} exists but the dispatch identity is not verified "
                    "(request_id marker/run not found); inspect GitHub before retrying"
                ),
            )
        )
    return Ok(
        PendingReconciliation(
            state="undetermined",
            detail="no dispatched run or release found; verify GitHub before retrying",
        )
    )


def _find_marker_run(
    *,
    workspace_root: Path,
    repo: str,
    request_id: str,
    attempts: int,
    delay_seconds: float,
):
    for attempt in range(max(1, attempts)):
        found = find_dispatched_run(
            workspace_root=workspace_root,
            repo_slug=repo,
            request_id=request_id,
        )
        if isinstance(found, Err):
            return found
        if found.value is not None:
            return found
        if attempt < attempts - 1 and delay_seconds > 0:
            sleep(delay_seconds)
    return Ok(None)


def _classify_run(
    *,
    workspace_root: Path,
    repo: str,
    workflow_file: str,
    run_id: int,
    run_url: str,
    tag: str,
    source_sha: str | None,
    tooling_sha: str | None,
    request_id: str,
    inputs: tuple[tuple[str, str], ...],
) -> Result[PendingReconciliation, ReleaseError]:
    payload = gh_api_json(
        workspace_root=workspace_root,
        endpoint=f"repos/{repo}/actions/runs/{run_id}",
    )
    if isinstance(payload, Err):
        return payload
    root = as_str_dict(payload.value)
    if root is None:
        return Err(ReleaseError(kind="workflow_failed", message="unexpected workflow run payload"))

    head_sha = get_str(root, "head_sha")
    values = dict(inputs)
    # Recompute from the run's immutable revision, never today's branch head.
    # Missing legacy inputs or inconsistent session fields cannot prove success.
    identity_matches = (
        bool(inputs)
        and len(values) == len(inputs)
        and values.get("tag") == tag
        and tooling_sha is not None
        and values.get("tooling_sha") == tooling_sha
        and (source_sha is None or values.get("source_sha") == source_sha)
        and get_str(root, "event") == "workflow_dispatch"
        and get_str(root, "path") == f".github/workflows/{workflow_file}"
        and head_sha is not None
        and dispatch_request_id(
            repo_slug=repo, workflow_file=workflow_file, ref=head_sha, inputs=inputs
        ) == request_id
    )
    if not identity_matches:
        return Ok(PendingReconciliation(
            state="undetermined",
            detail="dispatch identity does not match the persisted inputs and workflow run",
            run_url=run_url,
        ))
    status = get_str(root, "status")
    conclusion = get_str(root, "conclusion")

    if status != "completed":
        return Ok(
            PendingReconciliation(
                state="in_flight",
                detail=f"workflow {workflow_file} is {status or 'unknown'}",
                run_url=run_url,
            )
        )
    if conclusion != "success":
        return Ok(
            PendingReconciliation(
                state="failed",
                detail=f"workflow {workflow_file} concluded {conclusion or 'unknown'}",
                run_url=run_url,
            )
        )

    released = release_exists_by_tag(workspace_root=workspace_root, repo=repo, tag=tag)
    if isinstance(released, Err):
        return released
    if released.value:
        identity = ".".join(sha[:12] for sha in (source_sha, tooling_sha) if sha)
        return Ok(
            PendingReconciliation(
                state="completed",
                detail=f"dispatched run succeeded and release {tag} is published ({identity})",
                run_url=run_url,
            )
        )
    return Ok(
        PendingReconciliation(
            state="undetermined",
            detail="dispatched workflow succeeded but release is not visible yet",
            run_url=run_url,
        )
    )
