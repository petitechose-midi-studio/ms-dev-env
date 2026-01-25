"""Multi-repository operations.

This module provides functions for working with multiple git repositories,
typically used for workspace management with open-control/ and midi-studio/.

Usage:
    from ms.git.multi import find_repos, status_all, pull_all

    repos = find_repos(workspace / "open-control")
    for path, status in status_all(repos):
        print(f"{path.name}: {status.branch}")
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from ms.core.result import Err, Ok
from ms.git.repository import GitError, GitStatus, Repository

if TYPE_CHECKING:
    pass

__all__ = [
    "PullResult",
    "RepoStatus",
    "find_repos",
    "pull_all",
    "status_all",
]


@dataclass(frozen=True, slots=True)
class RepoStatus:
    """Status of a repository.

    Attributes:
        path: Repository path
        status: Git status if successful, None on error
        error: Error if status failed, None on success
    """

    path: Path
    status: GitStatus | None = None
    error: GitError | None = None

    @property
    def ok(self) -> bool:
        """True if status was retrieved successfully."""
        return self.status is not None

    @property
    def is_clean(self) -> bool:
        """True if repository is clean. False if dirty or error."""
        return self.status is not None and self.status.is_clean

    @property
    def is_dirty(self) -> bool:
        """True if repository has changes."""
        return self.status is not None and not self.status.is_clean

    @property
    def has_divergence(self) -> bool:
        """True if repository has diverged from upstream."""
        return self.status is not None and self.status.has_divergence


@dataclass(frozen=True, slots=True)
class PullResult:
    """Result of pulling a repository.

    Attributes:
        path: Repository path
        output: Pull output if successful, None on error
        error: Error if pull failed, None on success
        skipped: True if pull was skipped (dirty, no upstream)
        skip_reason: Reason for skipping if skipped
    """

    path: Path
    output: str | None = None
    error: GitError | None = None
    skipped: bool = False
    skip_reason: str | None = None

    @property
    def ok(self) -> bool:
        """True if pull was successful."""
        return self.output is not None


def find_repos(base: Path) -> list[Path]:
    """Find all git repositories in a directory.

    Searches one level deep for directories containing .git.

    Args:
        base: Directory to search

    Returns:
        Sorted list of repository paths
    """
    if not base.is_dir():
        return []

    repos: list[Path] = []

    for child in base.iterdir():
        if not child.is_dir():
            continue
        if (child / ".git").exists():
            repos.append(child)

    return sorted(repos, key=lambda p: p.name.lower())


def find_workspace_repos(workspace: Path) -> list[Path]:
    """Find all repositories in a workspace.

    Searches:
    - workspace root (if it's a repo)
    - open-control/*
    - midi-studio/*

    Args:
        workspace: Workspace root directory

    Returns:
        List of repository paths
    """
    repos: list[Path] = []

    # Check if workspace root is a repo
    if (workspace / ".git").exists():
        repos.append(workspace)

    # Find repos in standard directories
    for subdir in ["open-control", "midi-studio"]:
        repos.extend(find_repos(workspace / subdir))

    return repos


def status_all(repos: list[Path]) -> list[RepoStatus]:
    """Get status of multiple repositories.

    Args:
        repos: List of repository paths

    Returns:
        List of RepoStatus for each repository
    """
    results: list[RepoStatus] = []

    for path in repos:
        repo = Repository(path)
        match repo.status():
            case Ok(status):
                results.append(RepoStatus(path=path, status=status))
            case Err(error):
                results.append(RepoStatus(path=path, error=error))

    return results


def pull_all(
    repos: list[Path],
    *,
    skip_dirty: bool = True,
    skip_no_upstream: bool = True,
) -> list[PullResult]:
    """Pull all repositories with fast-forward only.

    Args:
        repos: List of repository paths
        skip_dirty: Skip repos with uncommitted changes
        skip_no_upstream: Skip repos without upstream configured

    Returns:
        List of PullResult for each repository
    """
    results: list[PullResult] = []

    for path in repos:
        repo = Repository(path)

        # Check if should skip
        if skip_dirty and not repo.is_clean():
            results.append(
                PullResult(
                    path=path,
                    skipped=True,
                    skip_reason="dirty",
                )
            )
            continue

        if skip_no_upstream and not repo.has_upstream():
            results.append(
                PullResult(
                    path=path,
                    skipped=True,
                    skip_reason="no upstream",
                )
            )
            continue

        # Pull
        match repo.pull_ff():
            case Ok(output):
                results.append(PullResult(path=path, output=output))
            case Err(error):
                results.append(PullResult(path=path, error=error))

    return results


def get_summary(statuses: list[RepoStatus]) -> dict[str, int]:
    """Get summary counts from repository statuses.

    Args:
        statuses: List of RepoStatus

    Returns:
        Dict with counts: total, clean, dirty, diverged, errors
    """
    return {
        "total": len(statuses),
        "clean": sum(1 for s in statuses if s.is_clean),
        "dirty": sum(1 for s in statuses if s.is_dirty),
        "diverged": sum(1 for s in statuses if s.has_divergence),
        "errors": sum(1 for s in statuses if not s.ok),
    }


def filter_dirty(statuses: list[RepoStatus]) -> list[RepoStatus]:
    """Filter to only dirty repositories.

    Args:
        statuses: List of RepoStatus

    Returns:
        List of dirty repositories
    """
    return [s for s in statuses if s.is_dirty]


def filter_diverged(statuses: list[RepoStatus]) -> list[RepoStatus]:
    """Filter to only diverged repositories.

    Args:
        statuses: List of RepoStatus

    Returns:
        List of diverged repositories
    """
    return [s for s in statuses if s.has_divergence]
