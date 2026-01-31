from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote

from ms.core.result import Err, Ok, Result
from ms.core.structured import as_obj_list, as_str_dict, get_list, get_str
from ms.platform.process import run as run_process
from ms.services.release.errors import ReleaseError
from ms.services.release.gh import gh_api_json


@dataclass(frozen=True, slots=True)
class CiStatus:
    green_head_shas: frozenset[str]

    def is_green(self, sha: str) -> bool:
        return sha in self.green_head_shas


def fetch_green_head_shas(
    *,
    workspace_root: Path,
    repo: str,
    workflow_file: str,
    branch: str,
    limit: int,
) -> Result[CiStatus, ReleaseError]:
    # workflow_file may contain slashes; GitHub requires it URL-encoded.
    wf = quote(workflow_file, safe="")
    endpoint = (
        f"repos/{repo}/actions/workflows/{wf}/runs"
        f"?branch={branch}&event=push&status=success&per_page={limit}"
    )

    obj = gh_api_json(workspace_root=workspace_root, endpoint=endpoint)
    if isinstance(obj, Err):
        return obj

    data = as_str_dict(obj.value)
    if data is None:
        return Err(
            ReleaseError(
                kind="invalid_input",
                message=f"unexpected workflow runs payload: {repo}",
            )
        )

    runs_obj = get_list(data, "workflow_runs")
    if runs_obj is None:
        return Err(
            ReleaseError(
                kind="invalid_input",
                message=f"missing workflow_runs: {repo}",
            )
        )

    runs = as_obj_list(runs_obj)
    if runs is None:
        return Err(
            ReleaseError(
                kind="invalid_input",
                message=f"invalid workflow_runs: {repo}",
            )
        )

    shas: set[str] = set()
    for run_obj in runs:
        run = as_str_dict(run_obj)
        if run is None:
            continue
        sha = get_str(run, "head_sha")
        if sha is None:
            continue
        if len(sha) != 40:
            continue
        shas.add(sha)

    return Ok(CiStatus(green_head_shas=frozenset(shas)))


def is_ci_green_for_sha(
    *,
    workspace_root: Path,
    repo: str,
    workflow: str,
    sha: str,
) -> Result[bool, ReleaseError]:
    cmd = [
        "gh",
        "run",
        "list",
        "--repo",
        repo,
        "--workflow",
        workflow,
        "--commit",
        sha,
        "--status",
        "success",
        "--limit",
        "1",
        "--json",
        "databaseId",
    ]

    result = run_process(cmd, cwd=workspace_root)
    if isinstance(result, Err):
        e = result.error
        return Err(
            ReleaseError(
                kind="invalid_input",
                message=f"failed to query CI status for {repo}@{sha}",
                hint=e.stderr.strip() or None,
            )
        )

    try:
        obj: object = json.loads(result.value)
    except json.JSONDecodeError as e:
        return Err(
            ReleaseError(
                kind="invalid_input",
                message=f"invalid JSON from gh run list: {e}",
                hint=repo,
            )
        )

    raw = as_obj_list(obj)
    if raw is None:
        return Err(
            ReleaseError(
                kind="invalid_input",
                message="unexpected gh run list payload",
                hint=repo,
            )
        )

    return Ok(len(raw) > 0)
