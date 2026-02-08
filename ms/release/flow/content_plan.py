from __future__ import annotations

from pathlib import Path

from ms.core.result import Err, Ok, Result
from ms.release.domain import config
from ms.release.domain.models import PinnedRepo, ReleaseBump, ReleaseChannel, ReleasePlan
from ms.release.domain.planner import ReleaseHistory, compute_history, suggest_tag, validate_tag
from ms.release.errors import ReleaseError
from ms.release.infra.github.client import list_distribution_releases


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

    return Ok(
        ReleasePlan(
            channel=channel,
            tag=tag,
            pinned=pinned,
            spec_path=spec_path,
            notes_path=notes_path,
            title=title,
        )
    )
