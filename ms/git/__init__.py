"""Git operations module.

This module provides abstractions for git operations:
- Repository: Single repository operations
- Multi-repo operations for workspace management

Usage:
    from ms.git import Repository, GitStatus

    repo = Repository(Path("/path/to/repo"))
    status = repo.status()
    if status.is_ok():
        print(f"Branch: {status.unwrap().branch}")

    # Multi-repo operations
    from ms.git import find_repos, status_all

    repos = find_repos(workspace / "open-control")
    for repo_status in status_all(repos):
        print(f"{repo_status.path.name}: {repo_status.status.branch}")
"""

from ms.git.multi import (
    PullResult,
    RepoStatus,
    filter_dirty,
    filter_diverged,
    find_repos,
    find_workspace_repos,
    get_summary,
    pull_all,
    status_all,
)
from ms.git.repository import (
    GitError,
    GitStatus,
    Repository,
    StatusEntry,
)

__all__ = [
    # Repository
    "GitError",
    "GitStatus",
    "Repository",
    "StatusEntry",
    # Multi
    "PullResult",
    "RepoStatus",
    "filter_dirty",
    "filter_diverged",
    "find_repos",
    "find_workspace_repos",
    "get_summary",
    "pull_all",
    "status_all",
]
