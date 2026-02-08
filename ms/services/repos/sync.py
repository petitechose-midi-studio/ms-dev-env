from __future__ import annotations

from ms.core.result import Err, Ok, Result
from ms.output.console import Style

from .git_ops import RepoGitOpsMixin
from .lockfile import write_lock_file
from .manifest import load_manifest
from .models import RepoError, RepoLockEntry, RepoSpec


class RepoSyncMixin(RepoGitOpsMixin):
    def sync_all(self, *, dry_run: bool = False) -> Result[None, RepoError]:
        specs_result = load_manifest(self._manifest_path)
        if isinstance(specs_result, Err):
            return specs_result
        specs = specs_result.value

        lock: list[RepoLockEntry] = []
        has_errors = False

        for spec in specs:
            entry = self._sync_repo(spec, dry_run=dry_run)
            if entry is None:
                has_errors = True
                continue
            lock.append(entry)

        if not dry_run:
            write_lock_file(workspace=self._workspace, lock=lock)

        if has_errors:
            return Err(
                RepoError(
                    kind="sync_failed",
                    message="some repositories failed to sync",
                )
            )
        return Ok(None)

    def _sync_repo(self, repo: RepoSpec, *, dry_run: bool) -> RepoLockEntry | None:
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
            result = self._run_git(cmd, cwd=self._workspace.root, network=True)
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

        if self._is_dirty(dest):
            self._console.print(f"skip dirty repo: {dest}", Style.WARNING)
            return RepoLockEntry(
                org=repo.org,
                name=repo.name,
                url=repo.url,
                default_branch=repo.branch,
                head_sha=self._head_sha(dest) if not dry_run else None,
            )

        current_branch = self._current_branch(dest)
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
                head_sha=self._head_sha(dest) if not dry_run else None,
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

        fetch_result = self._run_git(
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
        pull_result = self._run_git(pull_cmd, cwd=self._workspace.root, network=True)
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
            head_sha=self._head_sha(dest),
        )
