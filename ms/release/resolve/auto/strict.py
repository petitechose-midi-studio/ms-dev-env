from __future__ import annotations

from pathlib import Path

from ms.core.result import Err, Ok, Result
from ms.release.domain.models import PinnedRepo, ReleaseRepo

from .diagnostics import RepoReadiness, local_repo_path, probe_release_readiness, resolve_repo_ref


def resolve_pinned_auto_strict(
    *,
    workspace_root: Path,
    repos: tuple[ReleaseRepo, ...],
    ref_overrides: dict[str, str],
) -> Result[tuple[PinnedRepo, ...], tuple[RepoReadiness, ...]]:
    checked: list[RepoReadiness] = []
    pinned: list[PinnedRepo] = []

    for repo in repos:
        ref = resolve_repo_ref(repo=repo, ref_overrides=ref_overrides)
        readiness = probe_release_readiness(workspace_root=workspace_root, repo=repo, ref=ref)
        if isinstance(readiness, Err):
            checked.append(
                RepoReadiness(
                    repo=repo,
                    ref=ref,
                    local_path=local_repo_path(workspace_root=workspace_root, repo=repo),
                    local_exists=False,
                    status=None,
                    local_head_sha=None,
                    remote_head_sha=None,
                    head_green=None,
                    error=readiness.error.message,
                )
            )
            continue
        checked.append(readiness.value)
        if readiness.value.remote_head_sha is not None:
            pinned.append(PinnedRepo(repo=repo, sha=readiness.value.remote_head_sha))

    blockers = tuple(entry for entry in checked if not entry.is_ready())
    if blockers:
        return Err(blockers)

    by_id = {entry.repo.id: entry for entry in pinned}
    ordered = tuple(by_id[repo.id] for repo in repos if repo.id in by_id)
    return Ok(ordered)
