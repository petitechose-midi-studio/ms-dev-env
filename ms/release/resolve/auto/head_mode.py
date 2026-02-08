from __future__ import annotations

from pathlib import Path

from ms.core.result import Err, Ok, Result
from ms.release.domain.models import PinnedRepo, ReleaseRepo

from .diagnostics import RepoReadiness, build_diag_blocker


def is_head_mode_repo(
    *,
    repo: ReleaseRepo,
    ref: str,
    ref_overrides: dict[str, str],
    head_repo_ids: frozenset[str],
) -> bool:
    explicit_ref = (repo.id in ref_overrides) and (ref != repo.ref)
    return (repo.id in head_repo_ids) or explicit_ref


def resolve_head_mode_pin(
    *,
    workspace_root: Path,
    repo: ReleaseRepo,
    ref: str,
    selected_repo: ReleaseRepo,
    diagnostics: RepoReadiness | None,
) -> Result[PinnedRepo, RepoReadiness]:
    if diagnostics is None or not diagnostics.is_ready():
        return Err(
            diagnostics
            if diagnostics is not None
            else build_diag_blocker(
                workspace_root=workspace_root,
                repo=repo,
                ref=ref,
                diagnostics=None,
                error="missing repo diagnostics",
            )
        )

    assert diagnostics.remote_head_sha is not None
    return Ok(PinnedRepo(repo=selected_repo, sha=diagnostics.remote_head_sha))
