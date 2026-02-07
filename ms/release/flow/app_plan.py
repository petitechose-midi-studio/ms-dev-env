from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from ms.core.result import Err, Ok, Result
from ms.release.domain.models import AppReleasePlan, PinnedRepo, ReleaseBump, ReleaseChannel
from ms.release.errors import ReleaseError


def build_app_release_plan(
    *,
    planner: Callable[..., Result[tuple[str, str], ReleaseError]],
    workspace_root: Path,
    channel: ReleaseChannel,
    bump: ReleaseBump,
    tag_override: str | None,
    pinned: tuple[PinnedRepo, ...],
) -> Result[AppReleasePlan, ReleaseError]:
    planned = planner(
        workspace_root=workspace_root,
        channel=channel,
        bump=bump,
        tag_override=tag_override,
        pinned=pinned,
    )
    if isinstance(planned, Err):
        return planned

    tag, version = planned.value
    return Ok(
        AppReleasePlan(
            channel=channel,
            tag=tag,
            version=version,
            pinned=pinned,
            title=f"release(app): {tag}",
        )
    )
