from __future__ import annotations

from ms.core.result import Err
from ms.core.workspace import Workspace
from ms.output.console import ConsoleProtocol, Style

from . import git_ops
from .models import RepoLockEntry, RepoSpec


class RepoSync:
    """Synchronize one checkout without owning workspace inventory or artifacts."""

    def __init__(self, *, workspace: Workspace, console: ConsoleProtocol) -> None:
        self._workspace = workspace
        self._console = console

    def sync_repo(self, repo: RepoSpec, *, dry_run: bool) -> RepoLockEntry | None:
        dest = self._workspace.root / repo.path

        if not dest.exists():
            self._console.print(f"clone {repo.org}/{repo.name} -> {dest}", Style.DIM)
            if dry_run:
                return RepoLockEntry(
                    org=repo.org,
                    name=repo.name,
                    url=repo.url,
                    default_branch=repo.branch,
                    head_sha=None,
                )

            dest.parent.mkdir(parents=True, exist_ok=True)
            cmd = ["git", "clone"]
            if repo.branch:
                cmd.extend(["--branch", repo.branch])
            cmd.extend([repo.url, str(dest)])
            result = git_ops.run_git(cmd, cwd=self._workspace.root, network=True)
            if isinstance(result, Err):
                self._console.print(f"git clone failed: {repo.org}/{repo.name}", Style.ERROR)
                stderr = result.error.stderr.strip()
                if stderr:
                    self._console.print(stderr, Style.DIM)
                return None

        if not (dest / ".git").exists():
            self._console.print(f"skip (not a git repo): {dest}", Style.WARNING)
            return RepoLockEntry(
                org=repo.org,
                name=repo.name,
                url=repo.url,
                default_branch=repo.branch,
                head_sha=None,
            )

        dirty = git_ops.is_dirty(dest)
        if dirty is None:
            self._console.print(f"skip (git status failed): {dest}", Style.WARNING)
            return RepoLockEntry(
                org=repo.org,
                name=repo.name,
                url=repo.url,
                default_branch=repo.branch,
                head_sha=None,
            )

        if dirty:
            self._console.print(f"skip dirty repo: {dest}", Style.WARNING)
            return RepoLockEntry(
                org=repo.org,
                name=repo.name,
                url=repo.url,
                default_branch=repo.branch,
                head_sha=git_ops.head_sha(dest) if not dry_run else None,
            )

        current_branch = git_ops.current_branch(dest)
        if repo.branch and current_branch and current_branch != repo.branch:
            self._console.print(
                f"skip (on branch {current_branch}, expected {repo.branch}): {dest}",
                Style.WARNING,
            )
            return RepoLockEntry(
                org=repo.org,
                name=repo.name,
                url=repo.url,
                default_branch=repo.branch,
                head_sha=git_ops.head_sha(dest) if not dry_run else None,
            )

        self._console.print(f"update {repo.org}/{repo.name}", Style.DIM)
        if dry_run:
            return RepoLockEntry(
                org=repo.org,
                name=repo.name,
                url=repo.url,
                default_branch=repo.branch,
                head_sha=None,
            )

        fetch_result = git_ops.run_git(
            ["git", "-C", str(dest), "fetch", "--prune", "origin"],
            cwd=self._workspace.root,
            network=True,
        )
        if isinstance(fetch_result, Err):
            self._console.print(f"git fetch failed: {dest}", Style.ERROR)
            stderr = fetch_result.error.stderr.strip()
            if stderr:
                self._console.print(stderr, Style.DIM)
            return None

        pull_cmd = ["git", "-C", str(dest), "pull", "--ff-only"]
        if repo.branch:
            pull_cmd.extend(["origin", repo.branch])
        pull_result = git_ops.run_git(pull_cmd, cwd=self._workspace.root, network=True)
        if isinstance(pull_result, Err):
            self._console.print(f"git pull --ff-only failed: {dest}", Style.ERROR)
            stderr = pull_result.error.stderr.strip()
            if stderr:
                self._console.print(stderr, Style.DIM)
            return None

        return RepoLockEntry(
            org=repo.org,
            name=repo.name,
            url=repo.url,
            default_branch=repo.branch,
            head_sha=git_ops.head_sha(dest),
        )
