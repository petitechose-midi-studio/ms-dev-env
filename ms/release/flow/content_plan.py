from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from ms.core.result import Result
from ms.release.domain.models import PinnedRepo, ReleaseBump, ReleaseChannel, ReleasePlan
from ms.release.errors import ReleaseError


def build_content_release_plan(
    *,
    planner: Callable[..., Result[ReleasePlan, ReleaseError]],
    workspace_root: Path,
    channel: ReleaseChannel,
    bump: ReleaseBump,
    tag_override: str | None,
    pinned: tuple[PinnedRepo, ...],
) -> Result[ReleasePlan, ReleaseError]:
    return planner(
        workspace_root=workspace_root,
        channel=channel,
        bump=bump,
        tag_override=tag_override,
        pinned=pinned,
    )
