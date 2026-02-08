from __future__ import annotations

from pathlib import Path

from ms.core.result import Err
from ms.release.domain.diagnostics import RepoReadiness
from ms.release.domain.models import PinnedRepo, ReleaseRepo
from ms.release.domain.open_control_models import OpenControlPreflightReport
from ms.release.infra.open_control import preflight_open_control
from ms.release.resolve.auto.diagnostics import (
    build_diag_blocker,
    probe_release_readiness,
    resolve_repo_ref,
)


def collect_release_preflight_issues(
    *,
    workspace_root: Path,
    release_repos: tuple[ReleaseRepo, ...],
    refs: dict[str, str],
) -> tuple[RepoReadiness, ...]:
    issues: list[RepoReadiness] = []
    for repo in release_repos:
        ref = resolve_repo_ref(repo=repo, ref_overrides=refs)
        readiness = probe_release_readiness(workspace_root=workspace_root, repo=repo, ref=ref)
        if isinstance(readiness, Err):
            issues.append(
                build_diag_blocker(
                    workspace_root=workspace_root,
                    repo=repo,
                    ref=ref,
                    diagnostics=None,
                    error=readiness.error.message,
                )
            )
            continue

        value = readiness.value
        if value.is_ready():
            continue
        issues.append(value)

    return tuple(issues)


def load_open_control_report(
    *,
    workspace_root: Path,
    pinned: tuple[PinnedRepo, ...],
) -> OpenControlPreflightReport | None:
    core = next((p for p in pinned if p.repo.id == "core"), None)
    if core is None:
        return None
    return preflight_open_control(workspace_root=workspace_root, core_sha=core.sha)
