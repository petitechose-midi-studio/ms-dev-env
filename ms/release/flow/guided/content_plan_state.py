from __future__ import annotations

from pathlib import Path

from ms.core.result import Err, Result
from ms.release.domain.models import ReleasePlan, ReleaseRepo
from ms.release.errors import ReleaseError

from .content_contracts import ContentGuidedDependencies
from .content_release_dispatch import validate_content_confirm_inputs
from .content_repo_pins import pinned
from .sessions import ContentReleaseSession


def resolve_content_release_plan(
    *,
    deps: ContentGuidedDependencies,
    workspace_root: Path,
    session: ContentReleaseSession,
    release_repos: tuple[ReleaseRepo, ...],
) -> Result[ReleasePlan, ReleaseError]:
    pinned_repos = pinned(session, release_repos=release_repos)
    if isinstance(pinned_repos, Err):
        return pinned_repos

    valid = validate_content_confirm_inputs(session)
    if isinstance(valid, Err):
        return valid
    channel, bump, tag = valid.value

    return deps.plan_release(
        workspace_root=workspace_root,
        channel=channel,
        bump=bump,
        tag_override=tag,
        pinned=pinned_repos.value,
    )
