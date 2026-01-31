from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path

from ms.core.result import Err, Ok, Result
from ms.core.structured import as_obj_list, as_str_dict, get_str, get_table
from ms.platform.process import run as run_process
from ms.services.release.errors import ReleaseError
from ms.services.release.model import DistributionRelease, RepoCommit


@dataclass(frozen=True, slots=True)
class GhViewer:
    login: str


def ensure_gh_available() -> Result[None, ReleaseError]:
    if shutil.which("gh") is None:
        return Err(
            ReleaseError(
                kind="gh_missing",
                message="gh: missing",
                hint="Install GitHub CLI: https://cli.github.com/",
            )
        )
    return Ok(None)


def ensure_gh_auth(*, workspace_root: Path) -> Result[None, ReleaseError]:
    result = run_process(["gh", "auth", "status"], cwd=workspace_root)
    if isinstance(result, Err):
        return Err(
            ReleaseError(
                kind="gh_auth_required",
                message="gh auth required",
                hint="Run: gh auth login",
            )
        )
    return Ok(None)


def gh_api_json(*, workspace_root: Path, endpoint: str) -> Result[object, ReleaseError]:
    result = run_process(["gh", "api", endpoint], cwd=workspace_root)
    if isinstance(result, Err):
        e = result.error
        return Err(
            ReleaseError(
                kind="invalid_input",
                message=f"gh api failed: {endpoint}",
                hint=e.stderr.strip() or None,
            )
        )

    try:
        obj: object = json.loads(result.value)
    except json.JSONDecodeError as e:
        return Err(
            ReleaseError(
                kind="invalid_input",
                message=f"gh api returned invalid JSON: {e}",
                hint=endpoint,
            )
        )

    return Ok(obj)


def viewer_permission(*, workspace_root: Path, repo: str) -> Result[str, ReleaseError]:
    # Use `gh repo view` since it is stable and does not require custom endpoints.
    result = run_process(
        ["gh", "repo", "view", repo, "--json", "viewerPermission"], cwd=workspace_root
    )
    if isinstance(result, Err):
        e = result.error
        return Err(
            ReleaseError(
                kind="invalid_input",
                message=f"failed to query repo permission: {repo}",
                hint=e.stderr.strip() or None,
            )
        )

    try:
        obj: object = json.loads(result.value)
    except json.JSONDecodeError as e:
        return Err(
            ReleaseError(
                kind="invalid_input",
                message=f"invalid JSON from gh repo view: {e}",
            )
        )

    data = as_str_dict(obj)
    if data is None:
        return Err(
            ReleaseError(
                kind="invalid_input",
                message="unexpected payload from gh repo view",
            )
        )

    perm = get_str(data, "viewerPermission")
    if perm is None:
        return Err(
            ReleaseError(
                kind="invalid_input",
                message="missing viewerPermission",
            )
        )

    return Ok(perm)


def current_user(*, workspace_root: Path) -> Result[GhViewer, ReleaseError]:
    result = gh_api_json(workspace_root=workspace_root, endpoint="user")
    if isinstance(result, Err):
        return result

    data = as_str_dict(result.value)
    if data is None:
        return Err(ReleaseError(kind="invalid_input", message="unexpected payload: user"))

    login = get_str(data, "login")
    if login is None:
        return Err(ReleaseError(kind="invalid_input", message="missing user.login"))
    return Ok(GhViewer(login=login))


def list_recent_commits(
    *,
    workspace_root: Path,
    repo: str,
    ref: str,
    limit: int,
) -> Result[list[RepoCommit], ReleaseError]:
    obj = gh_api_json(
        workspace_root=workspace_root,
        endpoint=f"repos/{repo}/commits?sha={ref}&per_page={limit}",
    )
    if isinstance(obj, Err):
        return obj

    raw = as_obj_list(obj.value)
    if raw is None:
        return Err(
            ReleaseError(kind="invalid_input", message=f"unexpected commits payload: {repo}")
        )

    out: list[RepoCommit] = []
    for item in raw:
        d = as_str_dict(item)
        if d is None:
            continue

        sha = get_str(d, "sha")
        if sha is None:
            continue

        commit_tbl = get_table(d, "commit")
        if commit_tbl is None:
            continue

        msg = get_str(commit_tbl, "message")
        if msg is None:
            continue

        date: str | None = None
        committer_tbl = get_table(commit_tbl, "committer")
        if committer_tbl is not None:
            date = get_str(committer_tbl, "date")

        # Keep only the first line for UI.
        first_line = msg.splitlines()[0].strip() if msg else msg
        out.append(RepoCommit(sha=sha, message=first_line, date_utc=date))

    return Ok(out)


def list_distribution_releases(
    *,
    workspace_root: Path,
    repo: str,
    limit: int,
) -> Result[list[DistributionRelease], ReleaseError]:
    obj = gh_api_json(
        workspace_root=workspace_root,
        endpoint=f"repos/{repo}/releases?per_page={limit}",
    )
    if isinstance(obj, Err):
        return obj

    raw = as_obj_list(obj.value)
    if raw is None:
        return Err(
            ReleaseError(kind="invalid_input", message=f"unexpected releases payload: {repo}")
        )

    out: list[DistributionRelease] = []
    for item in raw:
        d = as_str_dict(item)
        if d is None:
            continue

        tag = get_str(d, "tag_name")
        if tag is None:
            continue

        prerelease_obj = d.get("prerelease")
        if not isinstance(prerelease_obj, bool):
            continue

        out.append(DistributionRelease(tag=tag, prerelease=prerelease_obj))

    return Ok(out)
