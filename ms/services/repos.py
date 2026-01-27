from __future__ import annotations

import json
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from ms.core.result import Err, Ok, Result
from ms.core.structured import as_obj_list, as_str_dict, get_str
from ms.core.workspace import Workspace
from ms.output.console import ConsoleProtocol, Style
from ms.platform.process import run as run_process

# -----------------------------------------------------------------------------
# Error Types
# -----------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class RepoError:
    """Error from repository sync operations."""

    kind: Literal["manifest_invalid", "sync_failed"]
    message: str
    hint: str | None = None


# -----------------------------------------------------------------------------
# Data Types
# -----------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class RepoSpec:
    org: str
    name: str
    url: str
    path: str
    branch: str | None = None


@dataclass(frozen=True, slots=True)
class RepoLockEntry:
    org: str
    name: str
    url: str
    default_branch: str | None
    head_sha: str | None


class RepoService:
    """Clone/update all repos from a pinned manifest (git-only).

    Policy:
    - Uses `git` only (no `gh`, no GH auth).
    - Never touches dirty repos.
    - Skips repos not on the expected branch.
    - Pulls with `--ff-only`.
    """

    def __init__(
        self,
        *,
        workspace: Workspace,
        console: ConsoleProtocol,
        manifest_path: Path | None = None,
    ) -> None:
        self._workspace = workspace
        self._console = console
        self._manifest_path = manifest_path or (
            Path(__file__).parent.parent / "data" / "repos.toml"
        )

    def sync_all(self, *, dry_run: bool = False) -> Result[None, RepoError]:
        specs_result = self._load_manifest(self._manifest_path)
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
            self._write_lock(lock)

        if has_errors:
            return Err(
                RepoError(
                    kind="sync_failed",
                    message="some repositories failed to sync",
                )
            )
        return Ok(None)

    def _load_manifest(self, path: Path) -> Result[list[RepoSpec], RepoError]:
        if not path.exists():
            return Err(
                RepoError(
                    kind="manifest_invalid",
                    message=f"repo manifest not found: {path}",
                    hint="Reinstall or update the workspace package",
                )
            )

        try:
            data_obj: object = tomllib.loads(path.read_text(encoding="utf-8"))
        except Exception as e:  # noqa: BLE001
            return Err(
                RepoError(
                    kind="manifest_invalid",
                    message=f"repo manifest is invalid TOML: {e}",
                )
            )

        data = as_str_dict(data_obj)
        if data is None:
            return Err(
                RepoError(
                    kind="manifest_invalid",
                    message="repo manifest root must be a TOML table",
                )
            )

        raw_obj = data.get("repos")
        if raw_obj is None:
            return Err(
                RepoError(
                    kind="manifest_invalid",
                    message="repo manifest missing 'repos' section",
                )
            )

        raw = as_obj_list(raw_obj)
        if raw is None:
            return Err(
                RepoError(
                    kind="manifest_invalid",
                    message="repo manifest 'repos' must be a list",
                )
            )

        specs: list[RepoSpec] = []
        for item in raw:
            item_dict = as_str_dict(item)
            if item_dict is None:
                continue

            org = get_str(item_dict, "org")
            name = get_str(item_dict, "name")
            url = get_str(item_dict, "url")
            rel_path = get_str(item_dict, "path")
            branch = get_str(item_dict, "branch")

            if org is None:
                continue
            if name is None:
                continue
            if url is None:
                continue
            if rel_path is None:
                continue

            repo_path = Path(rel_path)
            if repo_path.is_absolute() or ".." in repo_path.parts:
                return Err(
                    RepoError(
                        kind="manifest_invalid",
                        message=f"invalid repo path in manifest: {rel_path}",
                    )
                )

            specs.append(
                RepoSpec(
                    org=org,
                    name=name,
                    url=url,
                    path=rel_path,
                    branch=branch,
                )
            )

        if not specs:
            return Err(
                RepoError(
                    kind="manifest_invalid",
                    message="repo manifest contains no repos",
                )
            )

        return Ok(specs)

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
            result = run_process(cmd, cwd=self._workspace.root)
            if isinstance(result, Err):
                self._console.print(f"git clone failed: {repo.org}/{repo.name}", Style.ERROR)
                stderr = result.error.stderr.strip()
                if stderr:
                    self._console.print(stderr, Style.DIM)
                return None

        # Update existing repo
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

        fetch_result = run_process(
            ["git", "-C", str(dest), "fetch", "--prune", "origin"],
            cwd=self._workspace.root,
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
        pull_result = run_process(pull_cmd, cwd=self._workspace.root)
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

    def _is_dirty(self, repo_dir: Path) -> bool:
        result = run_process(
            ["git", "-C", str(repo_dir), "status", "--porcelain"],
            cwd=repo_dir,
        )
        match result:
            case Ok(stdout):
                return bool(stdout.strip())
            case Err(_):
                return False
            case _:
                return False

    def _current_branch(self, repo_dir: Path) -> str | None:
        result = run_process(
            ["git", "-C", str(repo_dir), "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=repo_dir,
        )
        match result:
            case Ok(stdout):
                value = stdout.strip()
                return value or None
            case Err(_):
                return None

    def _head_sha(self, repo_dir: Path) -> str | None:
        result = run_process(
            ["git", "-C", str(repo_dir), "rev-parse", "HEAD"],
            cwd=repo_dir,
        )
        match result:
            case Ok(stdout):
                value = stdout.strip()
                return value or None
            case Err(_):
                return None
