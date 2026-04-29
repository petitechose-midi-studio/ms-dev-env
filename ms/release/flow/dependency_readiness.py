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
    return ", ".join(parts) if parts else "working tree has local changes"
