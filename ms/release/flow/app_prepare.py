from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from ms.core.result import Err, Ok, Result
from ms.output.console import ConsoleProtocol
from ms.release.domain.models import AppReleasePlan
from ms.release.errors import ReleaseError


class AppPrepareResultLike(Protocol):
    @property
    def pr_url(self) -> str: ...

    @property
    def source_sha(self) -> str: ...


@dataclass(frozen=True, slots=True)
class PreparedAppRelease:
    plan: AppReleasePlan
    pr_url: str
    source_sha: str


def prepare_app_release_distribution[PrepareT: AppPrepareResultLike](
    *,
    ensure_ci_green_fn: Callable[..., Result[None, ReleaseError]],
    prepare_app_pr_fn: Callable[..., Result[PrepareT, ReleaseError]],
    workspace_root: Path,
    console: ConsoleProtocol,
    plan: AppReleasePlan,
    allow_non_green: bool,
    dry_run: bool,
) -> Result[PreparedAppRelease, ReleaseError]:
    green = ensure_ci_green_fn(
        workspace_root=workspace_root,
        pinned=plan.pinned,
        allow_non_green=allow_non_green,
    )
    if isinstance(green, Err):
        return green

    prepared = prepare_app_pr_fn(
        workspace_root=workspace_root,
        console=console,
        tag=plan.tag,
        version=plan.version,
        base_sha=plan.pinned[0].sha,
        pinned=plan.pinned,
        dry_run=dry_run,
    )
    if isinstance(prepared, Err):
        return prepared

    return Ok(
        PreparedAppRelease(
            plan=plan,
            pr_url=prepared.value.pr_url,
            source_sha=prepared.value.source_sha,
        )
    )
