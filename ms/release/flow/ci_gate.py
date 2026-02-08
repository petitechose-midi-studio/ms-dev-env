from __future__ import annotations

from pathlib import Path

from ms.core.result import Err, Ok, Result
from ms.release.domain.models import PinnedRepo
from ms.release.errors import ReleaseError
from ms.release.infra.github.ci import is_ci_green_for_sha


def ensure_ci_green(
    *,
    workspace_root: Path,
    pinned: tuple[PinnedRepo, ...],
    allow_non_green: bool,
) -> Result[None, ReleaseError]:
    for item in pinned:
        workflow = item.repo.required_ci_workflow_file
        if workflow is None:
            continue

        green = is_ci_green_for_sha(
            workspace_root=workspace_root,
            repo=item.repo.slug,
            workflow=workflow,
            sha=item.sha,
        )
        if isinstance(green, Err):
            return green

        if green.value:
            continue
        if allow_non_green:
            continue

        return Err(
            ReleaseError(
                kind="ci_not_green",
                message=f"CI not green for {item.repo.slug}@{item.sha}",
                hint="Pick a SHA with successful CI, or pass --allow-non-green.",
            )
        )

    return Ok(None)
