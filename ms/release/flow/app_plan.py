from __future__ import annotations

from pathlib import Path

from ms.core.result import Err, Ok, Result
from ms.release.domain import config
from ms.release.domain.models import AppReleasePlan, PinnedRepo, ReleaseBump, ReleaseChannel
from ms.release.domain.planner import ReleaseHistory, compute_history, suggest_tag, validate_tag
from ms.release.errors import ReleaseError
from ms.release.infra.artifacts.app_version_writer import version_from_tag
from ms.release.infra.github.client import list_distribution_releases


def load_app_history(*, workspace_root: Path) -> Result[ReleaseHistory, ReleaseError]:
    releases = list_distribution_releases(
        workspace_root=workspace_root,
        repo=config.APP_REPO_SLUG,
        limit=100,
    )
    if isinstance(releases, Err):
        return releases
    return Ok(compute_history(releases.value))


def plan_app_release(
    *,
    workspace_root: Path,
    channel: ReleaseChannel,
    bump: ReleaseBump,
    tag_override: str | None,
    pinned: tuple[PinnedRepo, ...],
) -> Result[AppReleasePlan, ReleaseError]:
    history_result = load_app_history(workspace_root=workspace_root)
    if isinstance(history_result, Err):
        return history_result
    history = history_result.value

    tag = tag_override or suggest_tag(channel=channel, bump=bump, history=history)
    valid = validate_tag(channel=channel, tag=tag, history=history)
    if isinstance(valid, Err):
        return valid

    version = version_from_tag(tag=tag)
    if isinstance(version, Err):
        return version

    return Ok(
        AppReleasePlan(
            channel=channel,
            tag=tag,
            version=version.value,
            pinned=pinned,
            title=f"release(app): {tag}",
        )
    )
