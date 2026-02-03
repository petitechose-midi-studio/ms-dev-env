from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ms.core.result import Err, Ok, Result
from ms.git.repository import GitError, GitStatus, Repository
from ms.platform.process import run as run_process
from ms.services.release.ci import fetch_green_head_shas
from ms.services.release.errors import ReleaseError
from ms.services.release.gh import get_ref_head_sha
from ms.services.release.model import PinnedRepo, ReleaseRepo


@dataclass(frozen=True, slots=True)
class RepoReadiness:
    repo: ReleaseRepo
    ref: str
    local_path: Path
    local_exists: bool
    status: GitStatus | None
    local_head_sha: str | None
    remote_head_sha: str | None
    head_green: bool | None
    error: str | None

    def is_ready(self) -> bool:
        if self.error is not None:
            return False
        if not self.local_exists:
            return False
        if self.status is None:
            return False
        if not self.status.is_clean:
            return False
        if self.status.upstream is None:
            return False
        if self.status.ahead != 0 or self.status.behind != 0:
            return False
        if self.local_head_sha is None or self.remote_head_sha is None:
            return False
        if self.local_head_sha != self.remote_head_sha:
            return False
        if self.repo.required_ci_workflow_file is None:
            return False
        return self.head_green is True


def _local_repo_path(*, workspace_root: Path, repo: ReleaseRepo) -> Path:
    name = repo.slug.split("/", 1)[-1]
    if repo.slug.startswith("petitechose-midi-studio/"):
        return workspace_root / "midi-studio" / name
    if repo.slug.startswith("open-control/"):
        return workspace_root / "open-control" / name
    return workspace_root / name


def _git_head_sha(*, repo_root: Path) -> str | None:
    r = run_process(["git", "rev-parse", "HEAD"], cwd=repo_root)
    if isinstance(r, Err):
        return None
    sha = r.value.strip()
    return sha if len(sha) == 40 else None


def probe_release_readiness(
    *,
    workspace_root: Path,
    repo: ReleaseRepo,
    ref: str,
) -> Result[RepoReadiness, ReleaseError]:
    local_path = _local_repo_path(workspace_root=workspace_root, repo=repo)
    local_repo = Repository(local_path)
    if not local_repo.exists():
        return Ok(
            RepoReadiness(
                repo=repo,
                ref=ref,
                local_path=local_path,
                local_exists=False,
                status=None,
                local_head_sha=None,
                remote_head_sha=None,
                head_green=None,
                error=None,
            )
        )

    st = local_repo.status()
    if isinstance(st, Err):
        e: GitError = st.error
        return Ok(
            RepoReadiness(
                repo=repo,
                ref=ref,
                local_path=local_path,
                local_exists=True,
                status=None,
                local_head_sha=None,
                remote_head_sha=None,
                head_green=None,
                error=f"git status failed: {e.message}",
            )
        )

    local_head = _git_head_sha(repo_root=local_path)

    remote_head_r = get_ref_head_sha(workspace_root=workspace_root, repo=repo.slug, ref=ref)
    if isinstance(remote_head_r, Err):
        return Ok(
            RepoReadiness(
                repo=repo,
                ref=ref,
                local_path=local_path,
                local_exists=True,
                status=st.value,
                local_head_sha=local_head,
                remote_head_sha=None,
                head_green=None,
                error=remote_head_r.error.message,
            )
        )

    remote_head = remote_head_r.value

    head_green: bool | None = None
    if repo.required_ci_workflow_file is not None:
        green_r = fetch_green_head_shas(
            workspace_root=workspace_root,
            repo=repo.slug,
            workflow_file=repo.required_ci_workflow_file,
            branch=ref,
            limit=30,
        )
        if isinstance(green_r, Err):
            return Ok(
                RepoReadiness(
                    repo=repo,
                    ref=ref,
                    local_path=local_path,
                    local_exists=True,
                    status=st.value,
                    local_head_sha=local_head,
                    remote_head_sha=remote_head,
                    head_green=None,
                    error=green_r.error.message,
                )
            )
        head_green = green_r.value.is_green(remote_head)

    return Ok(
        RepoReadiness(
            repo=repo,
            ref=ref,
            local_path=local_path,
            local_exists=True,
            status=st.value,
            local_head_sha=local_head,
            remote_head_sha=remote_head,
            head_green=head_green,
            error=None,
        )
    )


def resolve_pinned_auto_strict(
    *,
    workspace_root: Path,
    repos: tuple[ReleaseRepo, ...],
    ref_overrides: dict[str, str],
) -> Result[tuple[PinnedRepo, ...], tuple[RepoReadiness, ...]]:
    checked: list[RepoReadiness] = []
    pinned: list[PinnedRepo] = []

    for r in repos:
        ref = ref_overrides.get(r.id, r.ref)
        rr = probe_release_readiness(workspace_root=workspace_root, repo=r, ref=ref)
        if isinstance(rr, Err):
            # This means we could not even probe; represent as an error entry.
            checked.append(
                RepoReadiness(
                    repo=r,
                    ref=ref,
                    local_path=_local_repo_path(workspace_root=workspace_root, repo=r),
                    local_exists=False,
                    status=None,
                    local_head_sha=None,
                    remote_head_sha=None,
                    head_green=None,
                    error=rr.error.message,
                )
            )
            continue
        checked.append(rr.value)
        if rr.value.remote_head_sha is not None:
            pinned.append(PinnedRepo(repo=r, sha=rr.value.remote_head_sha))

    blockers = tuple(r for r in checked if not r.is_ready())
    if blockers:
        return Err(blockers)

    # Preserve repo order from config.
    by_id = {p.repo.id: p for p in pinned}
    out = tuple(by_id[r.id] for r in repos if r.id in by_id)
    return Ok(out)
