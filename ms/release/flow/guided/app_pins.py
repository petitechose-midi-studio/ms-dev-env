from __future__ import annotations

from ms.core.result import Err, Ok, Result
from ms.release.domain.models import PinnedRepo, ReleaseRepo
from ms.release.errors import ReleaseError

from .sessions import AppReleaseSession


def pinned_app_repo(
    *,
    app_release_repo: ReleaseRepo,
    session: AppReleaseSession,
) -> Result[tuple[PinnedRepo, ...], ReleaseError]:
    if session.repo_sha is None:
        return Err(ReleaseError(kind="invalid_input", message="missing selected app source sha"))

    repo = ReleaseRepo(
        id=app_release_repo.id,
        slug=app_release_repo.slug,
        ref=session.repo_ref,
        required_ci_workflow_file=app_release_repo.required_ci_workflow_file,
    )
    return Ok((PinnedRepo(repo=repo, sha=session.repo_sha),))
