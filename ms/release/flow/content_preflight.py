from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Protocol

from ms.core.result import Err, Result
from ms.release.domain.models import PinnedRepo, ReleaseRepo
from ms.release.errors import ReleaseError


class SupportsReady(Protocol):
    def is_ready(self) -> bool: ...


def collect_release_preflight_issues[ReadinessT: SupportsReady](
    *,
    workspace_root: Path,
    release_repos: tuple[ReleaseRepo, ...],
    refs: dict[str, str],
    probe_readiness_fn: Callable[..., Result[ReadinessT, ReleaseError]],
    make_error_readiness_fn: Callable[[ReleaseRepo, str, str], ReadinessT],
) -> tuple[ReadinessT, ...]:
    issues: list[ReadinessT] = []
    for repo in release_repos:
        ref = refs.get(repo.id, repo.ref)
        readiness = probe_readiness_fn(workspace_root=workspace_root, repo=repo, ref=ref)
        if isinstance(readiness, Err):
            issues.append(make_error_readiness_fn(repo, ref, readiness.error.message))
            continue

        value = readiness.value
        if value.is_ready():
            continue
        issues.append(value)

    return tuple(issues)


def load_open_control_report[ReportT](
    *,
    workspace_root: Path,
    pinned: tuple[PinnedRepo, ...],
    preflight_fn: Callable[..., ReportT],
) -> ReportT | None:
    core = next((p for p in pinned if p.repo.id == "core"), None)
    if core is None:
        return None
    return preflight_fn(workspace_root=workspace_root, core_sha=core.sha)
