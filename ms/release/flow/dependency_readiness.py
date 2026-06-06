from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Protocol

from ms.core.result import Err, Ok, Result
from ms.git.repository import GitError, GitStatus, Repository
from ms.release.domain.dependency_graph_models import ReleaseGraph, ReleaseGraphNode
from ms.release.domain.dependency_readiness_models import (
    DependencyReadinessItem,
    DependencyReadinessReport,
)
from ms.release.errors import ReleaseError
from ms.release.infra.github.client import get_ref_head_sha


class ReadinessRepository(Protocol):
    def exists(self) -> bool: ...

    def fetch(self) -> Result[str, GitError]: ...

    def status(self) -> Result[GitStatus, GitError]: ...

    def current_branch(self) -> str | None: ...

    def head_sha(self) -> Result[str, GitError]: ...


RepoFactory = Callable[[Path], ReadinessRepository]
FetchableChecker = Callable[[str, str], Result[bool, ReleaseError]]


def assess_dependency_readiness(
    *,
    workspace_root: Path,
    graph: ReleaseGraph,
    repo_factory: RepoFactory = Repository,
    fetchable_checker: FetchableChecker | None = None,
    enforce_expected_branch: bool = False,
    refresh_remotes: bool = False,
) -> DependencyReadinessReport:
    def default_fetchable_checker(repo: str, sha: str) -> Result[bool, ReleaseError]:
        return is_commit_fetchable(
            workspace_root=workspace_root,
            repo=repo,
            sha=sha,
        )

    checker: FetchableChecker = fetchable_checker or default_fetchable_checker

    items: list[DependencyReadinessItem] = []
    by_node_id: dict[str, DependencyReadinessItem] = {}
    for node in graph.nodes:
        item = _assess_node(
            workspace_root=workspace_root,
            node=node,
            repo_factory=repo_factory,
            fetchable_checker=checker,
            enforce_expected_branch=enforce_expected_branch,
            refresh_remotes=refresh_remotes,
        )

        blocked_by = [
            dependency
            for dependency in node.depends_on
            if by_node_id.get(dependency) is not None and by_node_id[dependency].is_blocking
        ]
        if item.status == "ok" and blocked_by:
            item = DependencyReadinessItem(
                node_id=node.id,
                repo=node.repo,
                path=item.path,
                status="blocked_by_dependency",
                sha=item.sha,
                branch=item.branch,
                detail=f"blocked by: {', '.join(blocked_by)}",
                hint="Resolve dependency blockers first, then rerun: uv run ms release",
            )

        items.append(item)
        by_node_id[node.id] = item

    return DependencyReadinessReport(items=tuple(items))


def is_commit_fetchable(
    *, workspace_root: Path, repo: str, sha: str
) -> Result[bool, ReleaseError]:
    resolved = get_ref_head_sha(workspace_root=workspace_root, repo=repo, ref=sha)
    if isinstance(resolved, Err):
        return Err(resolved.error)
    return Ok(resolved.value == sha)


def _assess_node(
    *,
    workspace_root: Path,
    node: ReleaseGraphNode,
    repo_factory: RepoFactory,
    fetchable_checker: FetchableChecker,
    enforce_expected_branch: bool,
    refresh_remotes: bool,
) -> DependencyReadinessItem:
    path = workspace_root / node.local_path
    repo = repo_factory(path)
    if not repo.exists():
        return DependencyReadinessItem(
            node_id=node.id,
            repo=node.repo,
            path=path,
            status="missing",
            detail=f"repository is unavailable: {path}",
            hint="Run: uv run ms sync --repos",
        )

    if refresh_remotes:
        fetched = repo.fetch()
        if isinstance(fetched, Err):
            return DependencyReadinessItem(
                node_id=node.id,
                repo=node.repo,
                path=path,
                status="repo_failed",
                detail=fetched.error.message,
                hint=f"Fetch repository before promotion: git -C {path} fetch",
            )

    status = repo.status()
    if isinstance(status, Err):
        return DependencyReadinessItem(
            node_id=node.id,
            repo=node.repo,
            path=path,
            status="repo_failed",
            detail=status.error.message,
            hint=f"Inspect repository: git -C {path} status",
        )

    branch = repo.current_branch()
    head = repo.head_sha()
    if isinstance(head, Err):
        return DependencyReadinessItem(
            node_id=node.id,
            repo=node.repo,
            path=path,
            status="repo_failed",
            branch=branch,
            detail=head.error.message,
            hint=f"Inspect repository: git -C {path} rev-parse HEAD",
        )
    sha = head.value

    if not status.value.is_clean:
        return DependencyReadinessItem(
            node_id=node.id,
            repo=node.repo,
            path=path,
            status="dirty",
            sha=sha,
            branch=branch,
            detail=_dirty_detail(status.value),
            hint=f"Commit, stash, or discard changes before promotion: git -C {path} status",
        )

    if branch is None:
        return DependencyReadinessItem(
            node_id=node.id,
            repo=node.repo,
            path=path,
            status="detached",
            sha=sha,
            detail="repository is in detached HEAD",
            hint="Checkout a branch or explicitly promote a published SHA in a later guided flow.",
        )

    expected_branch = node.expected_branch if enforce_expected_branch else None
    if expected_branch is not None and branch != expected_branch:
        return DependencyReadinessItem(
            node_id=node.id,
            repo=node.repo,
            path=path,
            status="wrong_branch",
            sha=sha,
            branch=branch,
            detail=f"branch {branch} is not release branch {expected_branch}",
            hint=(
                "Merge this branch if its changes are required, then switch to the "
                f"release branch before promotion: "
                f"git -C {path} switch {expected_branch}"
            ),
        )

    if status.value.upstream is None:
        return DependencyReadinessItem(
            node_id=node.id,
            repo=node.repo,
            path=path,
            status="no_upstream",
            sha=sha,
            branch=branch,
            detail=f"branch {branch} has no upstream",
            hint=f"Set an upstream or push the branch: git -C {path} push -u origin {branch}",
        )

    expected_upstream = f"origin/{expected_branch}" if expected_branch is not None else None
    if expected_upstream is not None and status.value.upstream != expected_upstream:
        return DependencyReadinessItem(
            node_id=node.id,
            repo=node.repo,
            path=path,
            status="wrong_upstream",
            sha=sha,
            branch=branch,
            detail=f"{branch} tracks {status.value.upstream}, expected {expected_upstream}",
            hint=(
                f"Track the canonical release branch before promotion: "
                f"git -C {path} branch --set-upstream-to={expected_upstream} {branch}"
            ),
        )

    if status.value.ahead and status.value.behind:
        return DependencyReadinessItem(
            node_id=node.id,
            repo=node.repo,
            path=path,
            status="diverged",
            sha=sha,
            branch=branch,
            detail=f"{branch} is ahead {status.value.ahead} and behind {status.value.behind}",
            hint=f"Resolve divergence before promotion: git -C {path} status",
        )

    if expected_branch is not None and status.value.ahead:
        return DependencyReadinessItem(
            node_id=node.id,
            repo=node.repo,
            path=path,
            status="ahead_remote",
            sha=sha,
            branch=branch,
            detail=f"{branch} is ahead of {status.value.upstream} by {status.value.ahead}",
            hint=(
                "Publish and merge this repository's release branch before promotion, "
                "then rerun: uv run ms release dependencies --dry-run"
            ),
        )

    fetchable = fetchable_checker(node.repo, sha)
    if isinstance(fetchable, Err):
        return DependencyReadinessItem(
            node_id=node.id,
            repo=node.repo,
            path=path,
            status="not_fetchable",
            sha=sha,
            branch=branch,
            detail=fetchable.error.message,
            hint=fetchable.error.hint
            or f"Push or merge this commit before promotion: git -C {path} push",
        )

    if status.value.ahead and not fetchable.value:
        return DependencyReadinessItem(
            node_id=node.id,
            repo=node.repo,
            path=path,
            status="ahead_unpushed",
            sha=sha,
            branch=branch,
            detail=f"{branch} is ahead of {status.value.upstream} by {status.value.ahead}",
            hint=f"Push this branch before promotion: git -C {path} push",
        )

    if not fetchable.value:
        return DependencyReadinessItem(
            node_id=node.id,
            repo=node.repo,
            path=path,
            status="not_fetchable",
            sha=sha,
            branch=branch,
            detail="HEAD commit is not fetchable from GitHub",
            hint=f"Push or merge this commit before promotion: git -C {path} push",
        )

    if status.value.behind:
        return DependencyReadinessItem(
            node_id=node.id,
            repo=node.repo,
            path=path,
            status="behind_remote",
            sha=sha,
            branch=branch,
            detail=f"{branch} is behind {status.value.upstream} by {status.value.behind}",
            hint=f"Update before promotion: git -C {path} pull --ff-only",
        )

    return DependencyReadinessItem(
        node_id=node.id,
        repo=node.repo,
        path=path,
        status="ok",
        sha=sha,
        branch=branch,
    )


def _dirty_detail(status: GitStatus) -> str:
    parts: list[str] = []
    if status.staged_count:
        parts.append(f"staged={status.staged_count}")
    if status.unstaged_count:
        parts.append(f"unstaged={status.unstaged_count}")
    if status.untracked_count:
        parts.append(f"untracked={status.untracked_count}")
    summary = ", ".join(parts) if parts else "working tree has local changes"
    entries = [f"  {entry.pretty_xy()} {entry.path}" for entry in status.entries]
    if not entries:
        return summary
    return "\n".join((summary, *entries))
