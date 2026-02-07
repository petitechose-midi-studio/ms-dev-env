from __future__ import annotations

import base64
import binascii
import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from time import sleep
from typing import Literal

from ms.core.result import Err, Ok, Result
from ms.core.structured import as_obj_list, as_str_dict, get_str, get_table
from ms.platform.process import ProcessError
from ms.platform.process import run as run_process
from ms.services.release.errors import ReleaseError
from ms.services.release.model import DistributionRelease, RepoCommit
from ms.services.release.timeouts import (
    GH_READ_RETRY_ATTEMPTS,
    GH_READ_RETRY_DELAY_SECONDS,
    GH_TIMEOUT_SECONDS,
)

_ReleaseErrorKind = Literal[
    "gh_missing",
    "gh_auth_required",
    "permission_denied",
    "invalid_input",
    "invalid_tag",
    "tag_exists",
    "ci_not_green",
    "dist_repo_dirty",
    "dist_repo_failed",
    "workflow_failed",
]


def _is_transient_gh_error(error: ProcessError) -> bool:
    text = f"{error.stderr}\n{error.stdout}".lower()
    markers = (
        "timed out",
        "timeout",
        "connection reset",
        "connection refused",
        "temporarily unavailable",
        "service unavailable",
        "bad gateway",
        "gateway timeout",
        "tls handshake timeout",
        "network is unreachable",
        "remote end hung up unexpectedly",
        "http 429",
        "http 500",
        "http 502",
        "http 503",
        "http 504",
    )
    if error.returncode == -1 and "timed out" in text:
        return True
    return any(marker in text for marker in markers)


def run_gh_read(
    *,
    workspace_root: Path,
    cmd: list[str],
    kind: _ReleaseErrorKind,
    message: str,
    hint: str | None = None,
    timeout: float = GH_TIMEOUT_SECONDS,
    retry_attempts: int = GH_READ_RETRY_ATTEMPTS,
) -> Result[str, ReleaseError]:
    attempts = max(1, retry_attempts)
    for attempt in range(attempts):
        result = run_process(cmd, cwd=workspace_root, timeout=timeout)
        if isinstance(result, Ok):
            return result

        error = result.error
        if attempt < attempts - 1 and _is_transient_gh_error(error):
            sleep(GH_READ_RETRY_DELAY_SECONDS * (attempt + 1))
            continue

        return Err(
            ReleaseError(
                kind=kind,
                message=message,
                hint=error.stderr.strip() or hint,
            )
        )

    return Err(ReleaseError(kind=kind, message=message, hint=hint))


@dataclass(frozen=True, slots=True)
class GhCompare:
    status: str
    ahead_by: int
    behind_by: int


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
    result = run_process(["gh", "auth", "status"], cwd=workspace_root, timeout=GH_TIMEOUT_SECONDS)
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
    result = run_gh_read(
        workspace_root=workspace_root,
        cmd=["gh", "api", endpoint],
        kind="invalid_input",
        message=f"gh api failed: {endpoint}",
        hint=endpoint,
    )
    if isinstance(result, Err):
        return result

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


def get_repo_file_text(
    *,
    workspace_root: Path,
    repo: str,
    path: str,
    ref: str,
) -> Result[str, ReleaseError]:
    # Use Contents API to avoid requiring a local checkout.
    endpoint = f"repos/{repo}/contents/{path}?ref={ref}"
    obj = gh_api_json(workspace_root=workspace_root, endpoint=endpoint)
    if isinstance(obj, Err):
        return obj

    data = as_str_dict(obj.value)
    if data is None:
        return Err(
            ReleaseError(
                kind="invalid_input",
                message=f"unexpected contents payload: {repo}/{path}",
                hint=endpoint,
            )
        )

    enc = get_str(data, "encoding")
    content = get_str(data, "content")
    if enc != "base64" or content is None:
        return Err(
            ReleaseError(
                kind="invalid_input",
                message=f"unexpected contents encoding for {repo}/{path}",
                hint=endpoint,
            )
        )

    try:
        raw = base64.b64decode(content, validate=False)
    except (binascii.Error, ValueError) as e:
        return Err(
            ReleaseError(
                kind="invalid_input",
                message=f"failed to decode contents: {e}",
                hint=endpoint,
            )
        )

    try:
        return Ok(raw.decode("utf-8"))
    except UnicodeDecodeError as e:
        return Err(
            ReleaseError(
                kind="invalid_input",
                message=f"invalid UTF-8 in contents: {e}",
                hint=endpoint,
            )
        )


def compare_commits(
    *,
    workspace_root: Path,
    repo: str,
    base: str,
    head: str,
) -> Result[GhCompare, ReleaseError]:
    obj = gh_api_json(
        workspace_root=workspace_root, endpoint=f"repos/{repo}/compare/{base}...{head}"
    )
    if isinstance(obj, Err):
        return obj

    data = as_str_dict(obj.value)
    if data is None:
        return Err(
            ReleaseError(
                kind="invalid_input",
                message=f"unexpected compare payload: {repo}",
            )
        )

    status = get_str(data, "status")
    if status is None:
        return Err(
            ReleaseError(
                kind="invalid_input",
                message=f"missing compare status: {repo}",
            )
        )

    ahead_by = data.get("ahead_by")
    behind_by = data.get("behind_by")
    if not isinstance(ahead_by, int) or not isinstance(behind_by, int):
        return Err(
            ReleaseError(
                kind="invalid_input",
                message=f"invalid compare ahead/behind: {repo}",
            )
        )

    return Ok(GhCompare(status=status, ahead_by=ahead_by, behind_by=behind_by))


def viewer_permission(*, workspace_root: Path, repo: str) -> Result[str, ReleaseError]:
    # Use `gh repo view` since it is stable and does not require custom endpoints.
    result = run_gh_read(
        workspace_root=workspace_root,
        cmd=["gh", "repo", "view", repo, "--json", "viewerPermission"],
        kind="invalid_input",
        message=f"failed to query repo permission: {repo}",
        hint=repo,
    )
    if isinstance(result, Err):
        return result

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


def get_ref_head_sha(*, workspace_root: Path, repo: str, ref: str) -> Result[str, ReleaseError]:
    obj = gh_api_json(workspace_root=workspace_root, endpoint=f"repos/{repo}/commits/{ref}")
    if isinstance(obj, Err):
        return obj

    data = as_str_dict(obj.value)
    if data is None:
        return Err(
            ReleaseError(
                kind="invalid_input",
                message=f"unexpected commit payload: {repo}@{ref}",
            )
        )

    sha = get_str(data, "sha")
    if sha is None or len(sha) != 40:
        return Err(
            ReleaseError(
                kind="invalid_input",
                message=f"invalid sha in commit payload: {repo}@{ref}",
            )
        )
    return Ok(sha)


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
