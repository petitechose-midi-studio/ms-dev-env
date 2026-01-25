from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from ms.core.workspace import Workspace
from ms.output.console import ConsoleProtocol, Style


@dataclass(frozen=True, slots=True)
class RepoRef:
    org: str
    name: str
    url: str
    default_branch: str | None
    archived: bool


@dataclass(frozen=True, slots=True)
class RepoLockEntry:
    org: str
    name: str
    url: str
    default_branch: str | None
    head_sha: str | None


class RepoService:
    """Clone/update all repos from configured GitHub orgs.

    Current policy (DEV):
    - Uses GitHub CLI (gh) + git
    - Clones via HTTPS
    - Tracks default branch at latest HEAD
    - Never touches dirty repos
    """

    ORGS: tuple[str, ...] = (
        "open-control",
        "petitechose-midi-studio",
    )

    def __init__(self, *, workspace: Workspace, console: ConsoleProtocol) -> None:
        self._workspace = workspace
        self._console = console

    def sync_all(self, *, limit: int = 200, dry_run: bool = False) -> bool:
        if not self._check_gh_auth():
            return False

        lock: list[RepoLockEntry] = []
        ok = True

        for org in self.ORGS:
            repos = self._list_org_repos(org, limit=limit)
            if repos is None:
                ok = False
                continue

            for repo in repos:
                if repo.archived:
                    continue

                dest = self._dest_dir_for_repo(org, repo.name)
                entry = self._sync_repo(repo, dest, dry_run=dry_run)
                if entry is None:
                    ok = False
                    continue
                lock.append(entry)

        if not dry_run:
            self._write_lock(lock)

        return ok

    def _check_gh_auth(self) -> bool:
        if not self._which("gh"):
            self._console.print("gh: missing", Style.ERROR)
            self._console.print("hint: install GitHub CLI (gh)", Style.DIM)
            return False

        proc = self._run(["gh", "auth", "status"], check=False)
        if proc.returncode != 0:
            self._console.print("gh auth: not logged in", Style.ERROR)
            self._console.print("hint: run `gh auth login`", Style.DIM)
            return False

        return True

    def _list_org_repos(self, org: str, *, limit: int) -> list[RepoRef] | None:
        cmd = [
            "gh",
            "repo",
            "list",
            org,
            "--limit",
            str(limit),
            "--json",
            "name,isArchived,defaultBranchRef,url",
        ]

        proc = self._run(cmd, check=False)
        if proc.returncode != 0:
            self._console.print(f"gh repo list failed for {org}", Style.ERROR)
            stderr = (proc.stderr or "").strip()
            if stderr:
                self._console.print(stderr, Style.DIM)
            return None

        try:
            raw: Any = json.loads(proc.stdout)
        except json.JSONDecodeError:
            self._console.print(f"gh repo list returned invalid JSON for {org}", Style.ERROR)
            return None

        if not isinstance(raw, list):
            self._console.print(f"gh repo list returned unexpected JSON for {org}", Style.ERROR)
            return None

        raw_list = cast(list[dict[str, Any]], raw)

        repos: list[RepoRef] = []
        for item_d in raw_list:
            name = item_d.get("name")
            url = item_d.get("url")
            is_archived = bool(item_d.get("isArchived", False))
            default_ref = item_d.get("defaultBranchRef")
            default_branch: str | None = None
            if isinstance(default_ref, dict):
                ref_name = cast(dict[str, Any], default_ref).get("name")
                if isinstance(ref_name, str) and ref_name:
                    default_branch = ref_name

            if not isinstance(name, str) or not name:
                continue
            if not isinstance(url, str) or not url:
                continue

            repos.append(
                RepoRef(
                    org=org,
                    name=name,
                    url=url,
                    default_branch=default_branch,
                    archived=is_archived,
                )
            )

        return repos

    def _dest_dir_for_repo(self, org: str, repo: str) -> Path:
        if org == "open-control":
            return self._workspace.root / "open-control" / repo
        return self._workspace.root / "midi-studio" / repo

    def _sync_repo(self, repo: RepoRef, dest: Path, *, dry_run: bool) -> RepoLockEntry | None:
        if not dest.exists():
            self._console.print(f"clone {repo.org}/{repo.name} -> {dest}", Style.DIM)
            if not dry_run:
                dest.parent.mkdir(parents=True, exist_ok=True)
                proc = self._run(["git", "clone", repo.url, str(dest)], check=False)
                if proc.returncode != 0:
                    self._console.print(f"git clone failed: {repo.org}/{repo.name}", Style.ERROR)
                    return None

        # Update existing repo
        if not (dest / ".git").exists():
            self._console.print(f"skip (not a git repo): {dest}", Style.WARNING)
            return RepoLockEntry(
                org=repo.org,
                name=repo.name,
                url=repo.url,
                default_branch=repo.default_branch,
                head_sha=None,
            )

        if self._is_dirty(dest):
            self._console.print(f"skip dirty repo: {dest}", Style.WARNING)
            return RepoLockEntry(
                org=repo.org,
                name=repo.name,
                url=repo.url,
                default_branch=repo.default_branch,
                head_sha=self._head_sha(dest) if not dry_run else None,
            )

        current_branch = self._current_branch(dest)
        if repo.default_branch and current_branch and current_branch != repo.default_branch:
            self._console.print(
                f"skip (on branch {current_branch}, default is {repo.default_branch}): {dest}",
                Style.WARNING,
            )
            return RepoLockEntry(
                org=repo.org,
                name=repo.name,
                url=repo.url,
                default_branch=repo.default_branch,
                head_sha=self._head_sha(dest) if not dry_run else None,
            )

        self._console.print(f"update {repo.org}/{repo.name}", Style.DIM)
        if not dry_run:
            self._run(["git", "-C", str(dest), "fetch", "--prune"], check=False)
            proc = self._run(["git", "-C", str(dest), "pull", "--ff-only"], check=False)
            if proc.returncode != 0:
                self._console.print(f"git pull --ff-only failed: {dest}", Style.WARNING)

        return RepoLockEntry(
            org=repo.org,
            name=repo.name,
            url=repo.url,
            default_branch=repo.default_branch,
            head_sha=self._head_sha(dest) if not dry_run else None,
        )

    def _write_lock(self, lock: list[RepoLockEntry]) -> None:
        self._workspace.state_dir.mkdir(parents=True, exist_ok=True)
        path = self._workspace.state_dir / "repos.lock.json"
        payload: list[dict[str, Any]] = [
            {
                "org": e.org,
                "name": e.name,
                "url": e.url,
                "default_branch": e.default_branch,
                "head_sha": e.head_sha,
            }
            for e in lock
        ]
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def _which(self, name: str) -> str | None:
        import shutil

        return shutil.which(name)

    def _run(self, args: list[str], *, check: bool) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            args,
            cwd=str(self._workspace.root),
            text=True,
            capture_output=True,
            check=check,
        )

    def _is_dirty(self, repo_dir: Path) -> bool:
        proc = subprocess.run(
            ["git", "-C", str(repo_dir), "status", "--porcelain"],
            text=True,
            capture_output=True,
            check=False,
        )
        return bool((proc.stdout or "").strip())

    def _current_branch(self, repo_dir: Path) -> str | None:
        proc = subprocess.run(
            ["git", "-C", str(repo_dir), "rev-parse", "--abbrev-ref", "HEAD"],
            text=True,
            capture_output=True,
            check=False,
        )
        if proc.returncode != 0:
            return None
        value = (proc.stdout or "").strip()
        return value or None

    def _head_sha(self, repo_dir: Path) -> str | None:
        proc = subprocess.run(
            ["git", "-C", str(repo_dir), "rev-parse", "HEAD"],
            text=True,
            capture_output=True,
            check=False,
        )
        if proc.returncode != 0:
            return None
        value = (proc.stdout or "").strip()
        return value or None
