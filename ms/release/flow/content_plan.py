from __future__ import annotations

from pathlib import Path

from ms.core.result import Err, Ok, Result
from ms.release.domain import config
from ms.release.domain.models import (
    PinnedRepo,
    ReleaseBump,
    ReleaseChannel,
    ReleasePlan,
    ReleaseTooling,
)
from ms.release.domain.planner import ReleaseHistory, compute_history, suggest_tag, validate_tag
from ms.release.errors import ReleaseError
from ms.release.infra.github.client import list_distribution_releases

from .release_tooling import resolve_release_tooling


def load_distribution_history(*, workspace_root: Path) -> Result[ReleaseHistory, ReleaseError]:
    releases = list_distribution_releases(
        workspace_root=workspace_root,
        repo=config.DIST_REPO_SLUG,
        limit=100,
    )
    if isinstance(releases, Err):
        return releases
    return Ok(compute_history(releases.value))


def plan_release(
    *,
    workspace_root: Path,
    channel: ReleaseChannel,
    bump: ReleaseBump,
    tag_override: str | None,
    pinned: tuple[PinnedRepo, ...],
    tooling_override: ReleaseTooling | None = None,
) -> Result[ReleasePlan, ReleaseError]:
    history_result = load_distribution_history(workspace_root=workspace_root)
    if isinstance(history_result, Err):
        return history_result
    history = history_result.value

    tag = tag_override or suggest_tag(channel=channel, bump=bump, history=history)
    valid = validate_tag(channel=channel, tag=tag, history=history)
    if isinstance(valid, Err):
        return valid

    spec_path = f"{config.DIST_SPEC_DIR}/{tag}.json"
    notes_path = f"{config.DIST_NOTES_DIR}/{tag}.md"
    title = f"release: {tag} ({channel})"
    if tooling_override is not None:
        tooling = tooling_override
    else:
        tooling_result = resolve_release_tooling(workspace_root=workspace_root)
        if isinstance(tooling_result, Err):
            return tooling_result
        tooling = tooling_result.value

    return Ok(
        ReleasePlan(
            channel=channel,
            tag=tag,
            pinned=pinned,
            tooling=tooling,
            spec_path=spec_path,
            notes_path=notes_path,
            title=title,
        )
    )
