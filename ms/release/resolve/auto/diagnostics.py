from __future__ import annotations

from pathlib import Path

from ms.core.result import Err, Ok, Result
from ms.git.repository import GitError, Repository
from ms.platform.process import run as run_process
from ms.release.domain import config
from ms.release.domain.diagnostics import RepoReadiness
from ms.release.domain.models import ReleaseRepo
from ms.release.errors import ReleaseError
from ms.release.infra.github.ci import fetch_green_head_shas
from ms.release.infra.github.client import get_ref_head_sha
from ms.release.infra.github.timeouts import GIT_TIMEOUT_SECONDS


def local_issue_reason(readiness: RepoReadiness) -> str:
    status = readiness.status
    if status is None:
        return "repo status unavailable"
    if not status.is_clean:
        return "working tree is dirty"
    if status.upstream is None:
        return "no upstream configured"
    if status.ahead:
        return f"ahead of upstream by {status.ahead}"
    if status.behind:
        return f"behind upstream by {status.behind}"
    return "repo not ready"


def local_repo_path(*, workspace_root: Path, repo: ReleaseRepo) -> Path:
    name = repo.slug.split("/", 1)[-1]
    if repo.slug == config.APP_REPO_SLUG:
        return workspace_root / config.APP_LOCAL_DIR
    if repo.slug.startswith("petitechose-midi-studio/"):
        return workspace_root / "midi-studio" / name
    if repo.slug.startswith("open-control/"):
        return workspace_root / "open-control" / name
    return workspace_root / name


def resolve_repo_ref(*, repo: ReleaseRepo, ref_overrides: dict[str, str]) -> str:
    override = ref_overrides.get(repo.id)
    return override if override is not None else repo.ref


def repo_with_ref(*, repo: ReleaseRepo, ref: str) -> ReleaseRepo:
    return ReleaseRepo(
        id=repo.id,
        slug=repo.slug,
        ref=ref,
        required_ci_workflow_file=repo.required_ci_workflow_file,
    )


def is_applyable_locally(readiness: RepoReadiness) -> bool:
    if not readiness.local_exists or readiness.status is None:
        return False
    if not readiness.status.is_clean:
        return False
    if readiness.status.upstream is None:
        return False
    return readiness.status.ahead == 0 and readiness.status.behind == 0


def build_diag_blocker(
    *,
    workspace_root: Path,
    repo: ReleaseRepo,
    ref: str,
    diagnostics: RepoReadiness | None,
    error: str,
) -> RepoReadiness:
    return RepoReadiness(
        repo=repo,
        ref=ref,
        local_path=local_repo_path(workspace_root=workspace_root, repo=repo),
        local_exists=(diagnostics.local_exists if diagnostics else False),
        status=(diagnostics.status if diagnostics else None),
        local_head_sha=(diagnostics.local_head_sha if diagnostics else None),
        remote_head_sha=(diagnostics.remote_head_sha if diagnostics else None),
        head_green=(diagnostics.head_green if diagnostics else None),
        error=error,
    )


def build_dist_blocker(
    *, workspace_root: Path, dist_repo_entry: ReleaseRepo, error: str
) -> RepoReadiness:
    return RepoReadiness(
        repo=dist_repo_entry,
        ref=dist_repo_entry.ref,
        local_path=workspace_root / "distribution",
        local_exists=False,
        status=None,
        local_head_sha=None,
        remote_head_sha=None,
        head_green=None,
        error=error,
    )


def _git_head_sha(*, repo_root: Path) -> str | None:
    result = run_process(["git", "rev-parse", "HEAD"], cwd=repo_root, timeout=GIT_TIMEOUT_SECONDS)
    if isinstance(result, Err):
        return None
    sha = result.value.strip()
    return sha if len(sha) == 40 else None


def probe_release_readiness(
    *,
    workspace_root: Path,
    repo: ReleaseRepo,
    ref: str,
) -> Result[RepoReadiness, ReleaseError]:
    repo_path = local_repo_path(workspace_root=workspace_root, repo=repo)
    local_repo = Repository(repo_path)
    if not local_repo.exists():
        return Ok(
            RepoReadiness(
                repo=repo,
                ref=ref,
                local_path=repo_path,
                local_exists=False,
                status=None,
                local_head_sha=None,
                remote_head_sha=None,
                head_green=None,
                error=None,
            )
        )

    status_result = local_repo.status()
    if isinstance(status_result, Err):
        error: GitError = status_result.error
        return Ok(
            RepoReadiness(
                repo=repo,
                ref=ref,
                local_path=repo_path,
                local_exists=True,
                status=None,
                local_head_sha=None,
                remote_head_sha=None,
                head_green=None,
                error=f"git status failed: {error.message}",
            )
        )

    local_head = _git_head_sha(repo_root=repo_path)

    remote_head_result = get_ref_head_sha(workspace_root=workspace_root, repo=repo.slug, ref=ref)
    if isinstance(remote_head_result, Err):
        return Ok(
            RepoReadiness(
                repo=repo,
                ref=ref,
                local_path=repo_path,
                local_exists=True,
                status=status_result.value,
                local_head_sha=local_head,
                remote_head_sha=None,
                head_green=None,
                error=remote_head_result.error.message,
            )
        )

    remote_head = remote_head_result.value

    head_green: bool | None = None
    if repo.required_ci_workflow_file is not None:
        green_result = fetch_green_head_shas(
            workspace_root=workspace_root,
            repo=repo.slug,
            workflow_file=repo.required_ci_workflow_file,
            branch=ref,
            limit=30,
        )
        if isinstance(green_result, Err):
            return Ok(
                RepoReadiness(
                    repo=repo,
                    ref=ref,
                    local_path=repo_path,
                    local_exists=True,
                    status=status_result.value,
                    local_head_sha=local_head,
                    remote_head_sha=remote_head,
                    head_green=None,
                    error=green_result.error.message,
                )
            )
        head_green = green_result.value.is_green(remote_head)

    return Ok(
        RepoReadiness(
            repo=repo,
            ref=ref,
            local_path=repo_path,
            local_exists=True,
            status=status_result.value,
            local_head_sha=local_head,
            remote_head_sha=remote_head,
            head_green=head_green,
            error=None,
        )
    )


def probe_repo_diagnostics(
    *,
    workspace_root: Path,
    repos: tuple[ReleaseRepo, ...],
    ref_overrides: dict[str, str],
) -> dict[str, RepoReadiness]:
    diagnostics: dict[str, RepoReadiness] = {}
    for repo in repos:
        ref = resolve_repo_ref(repo=repo, ref_overrides=ref_overrides)
        readiness = probe_release_readiness(workspace_root=workspace_root, repo=repo, ref=ref)
        if isinstance(readiness, Ok):
            diagnostics[repo.id] = readiness.value
    return diagnostics
