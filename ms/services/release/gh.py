from __future__ import annotations

from pathlib import Path
from typing import Literal

from ms.core.result import Result
from ms.release.domain.models import DistributionRelease, RepoCommit
from ms.release.errors import ReleaseError
from ms.release.infra.github import client as _client
from ms.release.infra.github.client import GhCompare, GhViewer

run_process = _client.run_process
sleep = _client.sleep

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


def _sync_test_patchpoints() -> None:
    _client.run_process = run_process
    _client.sleep = sleep


def run_gh_read(
    *,
    workspace_root: Path,
    cmd: list[str],
    kind: _ReleaseErrorKind,
    message: str,
    hint: str | None = None,
    timeout: float = _client.GH_TIMEOUT_SECONDS,
    retry_attempts: int = _client.GH_READ_RETRY_ATTEMPTS,
) -> Result[str, ReleaseError]:
    _sync_test_patchpoints()
    return _client.run_gh_read(
        workspace_root=workspace_root,
        cmd=cmd,
        kind=kind,
        message=message,
        hint=hint,
        timeout=timeout,
        retry_attempts=retry_attempts,
    )


def ensure_gh_available() -> Result[None, ReleaseError]:
    _sync_test_patchpoints()
    return _client.ensure_gh_available()


def ensure_gh_auth(*, workspace_root: Path) -> Result[None, ReleaseError]:
    _sync_test_patchpoints()
    return _client.ensure_gh_auth(workspace_root=workspace_root)


def gh_api_json(*, workspace_root: Path, endpoint: str) -> Result[object, ReleaseError]:
    _sync_test_patchpoints()
    return _client.gh_api_json(workspace_root=workspace_root, endpoint=endpoint)


def get_repo_file_text(
    *,
    workspace_root: Path,
    repo: str,
    path: str,
    ref: str,
) -> Result[str, ReleaseError]:
    _sync_test_patchpoints()
    return _client.get_repo_file_text(
        workspace_root=workspace_root,
        repo=repo,
        path=path,
        ref=ref,
    )


def compare_commits(
    *,
    workspace_root: Path,
    repo: str,
    base: str,
    head: str,
) -> Result[GhCompare, ReleaseError]:
    _sync_test_patchpoints()
    return _client.compare_commits(
        workspace_root=workspace_root,
        repo=repo,
        base=base,
        head=head,
    )


def viewer_permission(*, workspace_root: Path, repo: str) -> Result[str, ReleaseError]:
    _sync_test_patchpoints()
    return _client.viewer_permission(workspace_root=workspace_root, repo=repo)


def current_user(*, workspace_root: Path) -> Result[GhViewer, ReleaseError]:
    _sync_test_patchpoints()
    return _client.current_user(workspace_root=workspace_root)


def list_recent_commits(
    *,
    workspace_root: Path,
    repo: str,
    ref: str,
    limit: int,
) -> Result[list[RepoCommit], ReleaseError]:
    _sync_test_patchpoints()
    return _client.list_recent_commits(
        workspace_root=workspace_root,
        repo=repo,
        ref=ref,
        limit=limit,
    )


def get_ref_head_sha(*, workspace_root: Path, repo: str, ref: str) -> Result[str, ReleaseError]:
    _sync_test_patchpoints()
    return _client.get_ref_head_sha(workspace_root=workspace_root, repo=repo, ref=ref)


def list_distribution_releases(
    *,
    workspace_root: Path,
    repo: str,
    limit: int,
) -> Result[list[DistributionRelease], ReleaseError]:
    _sync_test_patchpoints()
    return _client.list_distribution_releases(
        workspace_root=workspace_root,
        repo=repo,
        limit=limit,
    )


__all__ = [
    "GhCompare",
    "GhViewer",
    "compare_commits",
    "current_user",
    "ensure_gh_auth",
    "ensure_gh_available",
    "get_ref_head_sha",
    "get_repo_file_text",
    "gh_api_json",
    "list_distribution_releases",
    "list_recent_commits",
    "run_gh_read",
    "viewer_permission",
]
