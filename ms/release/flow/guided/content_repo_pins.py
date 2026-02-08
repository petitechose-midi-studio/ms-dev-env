from __future__ import annotations

from dataclasses import replace

from ms.core.result import Err, Ok, Result
from ms.release.domain.models import PinnedRepo, ReleaseRepo
from ms.release.errors import ReleaseError

from .sessions import ContentReleaseSession


def sha_map(session: ContentReleaseSession) -> dict[str, str]:
    return {repo_id: sha for repo_id, sha in session.repo_shas}


def set_sha(
    session: ContentReleaseSession,
    *,
    release_repos: tuple[ReleaseRepo, ...],
    repo_id: str,
    sha: str,
) -> ContentReleaseSession:
    by_id = sha_map(session)
    by_id[repo_id] = sha
    ordered = tuple((repo.id, by_id[repo.id]) for repo in release_repos if repo.id in by_id)
    return replace(session, repo_shas=ordered)


def pinned(
    session: ContentReleaseSession,
    *,
    release_repos: tuple[ReleaseRepo, ...],
) -> Result[tuple[PinnedRepo, ...], ReleaseError]:
    by_id = sha_map(session)
    missing = [repo.id for repo in release_repos if repo.id not in by_id]
    if missing:
        return Err(
            ReleaseError(
                kind="invalid_input",
                message=f"missing selected source sha for: {', '.join(missing)}",
            )
        )
    return Ok(tuple(PinnedRepo(repo=repo, sha=by_id[repo.id]) for repo in release_repos))
