from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from time import sleep
from urllib.parse import quote

from ms.core.result import Err, Ok, Result
from ms.core.structured import as_str_dict, get_int, get_list, get_str, get_table
from ms.release.errors import ReleaseError

from .gh_base import run_gh_process
from .timeouts import GH_TIMEOUT_SECONDS

_LOOKUP_MAX_ATTEMPTS = 20
_LOOKUP_DELAY_SECONDS = 2.0


@dataclass(frozen=True, slots=True)
class WorkflowRunResolution:
    run_id: int
    url: str


def dispatch_marker_name(*, request_id: str) -> str:
    return f"dispatch-{request_id}"


def resolve_dispatched_run(
    *,
    workspace_root: Path,
    repo_slug: str,
    request_id: str,
) -> Result[WorkflowRunResolution, ReleaseError]:
    marker_name = dispatch_marker_name(request_id=request_id)
    cmd = ["gh", "api", _artifact_lookup_endpoint(repo_slug=repo_slug, marker_name=marker_name)]

    for attempt in range(_LOOKUP_MAX_ATTEMPTS):
        result = run_gh_process(cmd, cwd=workspace_root, timeout=GH_TIMEOUT_SECONDS)
        if isinstance(result, Err):
            e = result.error
            return Err(
                ReleaseError(
                    kind="workflow_failed",
                    message="failed to query workflow artifacts",
                    hint=e.stderr.strip() or None,
                )
            )

        resolved = _find_dispatched_run(
            payload=result.value,
            repo_slug=repo_slug,
            marker_name=marker_name,
        )
        if isinstance(resolved, Err):
            return resolved
        if resolved.value is not None:
            return Ok(resolved.value)
        if attempt < _LOOKUP_MAX_ATTEMPTS - 1:
            sleep(_LOOKUP_DELAY_SECONDS)

    return Err(
        ReleaseError(
            kind="workflow_failed",
            message="could not deterministically identify the dispatched workflow run",
            hint=(
                f"Dispatch marker artifact {marker_name} was not found; "
                "check Actions and ensure the workflow uploads its dispatch marker artifact."
            ),
        )
    )


def _artifact_lookup_endpoint(*, repo_slug: str, marker_name: str) -> str:
    encoded_name = quote(marker_name, safe="")
    return f"repos/{repo_slug}/actions/artifacts?per_page=100&name={encoded_name}"


def _find_dispatched_run(
    *,
    payload: str,
    repo_slug: str,
    marker_name: str,
) -> Result[WorkflowRunResolution | None, ReleaseError]:
    try:
        obj: object = json.loads(payload)
    except json.JSONDecodeError as exc:
        return Err(
            ReleaseError(
                kind="workflow_failed",
                message=f"invalid JSON from gh api artifacts: {exc}",
            )
        )

    root = as_str_dict(obj)
    if root is None:
        return Err(ReleaseError(kind="workflow_failed", message="unexpected artifact payload"))

    artifacts = get_list(root, "artifacts")
    if artifacts is None:
        return Err(ReleaseError(kind="workflow_failed", message="missing artifacts in response"))

    for item in artifacts:
        artifact = as_str_dict(item)
        if artifact is None:
            continue
        if get_str(artifact, "name") != marker_name:
            continue
        if artifact.get("expired") is True:
            continue
        workflow_run = get_table(artifact, "workflow_run")
        if workflow_run is None:
            continue
        run_id = get_int(workflow_run, "id")
        if run_id is None:
            continue
        return Ok(
            WorkflowRunResolution(
                run_id=run_id,
                url=f"https://github.com/{repo_slug}/actions/runs/{run_id}",
            )
        )

    return Ok(None)
