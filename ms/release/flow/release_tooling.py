from __future__ import annotations

from pathlib import Path

from ms.core.result import Err, Ok, Result
from ms.release.domain import CandidateInputRepo
from ms.release.domain.config import MS_DEFAULT_BRANCH, MS_REPO_SLUG
from ms.release.domain.models import ReleaseTooling
from ms.release.errors import ReleaseError
from ms.release.infra.repos.git_ops import run_git_command


def resolve_release_tooling(*, workspace_root: Path) -> Result[ReleaseTooling, ReleaseError]:
    head = run_git_command(cmd=["git", "rev-parse", "HEAD"], repo_root=workspace_root)
    if isinstance(head, Err):
        error = head.error
        return Err(
            ReleaseError(
                kind="repo_failed",
                message="failed to resolve release tooling sha",
                hint=error.stderr.strip() or None,
            )
        )

    sha = head.value.strip()
    if len(sha) != 40:
        return Err(
            ReleaseError(
                kind="repo_failed",
                message="invalid release tooling sha",
                hint=sha,
            )
        )

    return Ok(ReleaseTooling(repo=MS_REPO_SLUG, ref=MS_DEFAULT_BRANCH, sha=sha))


def ensure_release_tooling_on_main(
    *, workspace_root: Path, tooling_sha: str
) -> Result[None, ReleaseError]:
    fetched = run_git_command(
        cmd=[
            "git",
            "fetch",
            "--no-tags",
            "origin",
            f"+refs/heads/{MS_DEFAULT_BRANCH}:refs/remotes/origin/{MS_DEFAULT_BRANCH}",
        ],
        repo_root=workspace_root,
        network=True,
    )
    if isinstance(fetched, Err):
        error = fetched.error
        return Err(
            ReleaseError(
                kind="repo_failed",
                message="failed to refresh release tooling main",
                hint=error.stderr.strip() or None,
            )
        )

    reachable = run_git_command(
        cmd=[
            "git",
            "merge-base",
            "--is-ancestor",
            tooling_sha,
            f"refs/remotes/origin/{MS_DEFAULT_BRANCH}",
        ],
        repo_root=workspace_root,
    )
    if isinstance(reachable, Err):
        return Err(
            ReleaseError(
                kind="invalid_input",
                message="release tooling SHA is not reachable from ms-dev-env main",
                hint=(
                    f"tooling SHA: {tooling_sha}\n"
                    f"repo: {MS_REPO_SLUG}\n"
                    "Merge this ms-dev-env commit to main before dispatching release workflows."
                ),
            )
        )

    return Ok(None)


def tooling_input_repo(*, tooling: ReleaseTooling) -> CandidateInputRepo:
    return CandidateInputRepo(id="ms-dev-env", repo=tooling.repo, sha=tooling.sha)
