"""Git repository abstraction.

This module provides the Repository class for single-repo git operations.
All operations return Result types for proper error handling.

Usage:
    repo = Repository(Path("/path/to/repo"))

    # Get status
    match repo.status():
        case Ok(status):
            print(f"Branch: {status.branch}")
            if status.is_clean:
                print("Working tree clean")
        case Err(e):
            print(f"Error: {e.message}")

    # Pull with fast-forward only
    match repo.pull_ff():
        case Ok(output):
            print(f"Pulled: {output}")
        case Err(e):
            print(f"Pull failed: {e.message}")
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from ms.core.result import Err, Ok, Result
from ms.platform.process import ProcessError
from ms.platform.process import run as run_process

_GIT_TIMEOUT_SECONDS = 30.0
_GIT_NETWORK_TIMEOUT_SECONDS = 3 * 60.0

__all__ = [
    "GitError",
    "GitStatus",
    "Repository",
    "StatusEntry",
]


@dataclass(frozen=True, slots=True)
class GitError:
    """Error from a git operation.

    Attributes:
        command: The git command that failed
        message: Error message
        returncode: Process return code
    """

    command: str
    message: str
    returncode: int = 1


@dataclass(frozen=True, slots=True)
class StatusEntry:
    """A single entry in git status.

    Attributes:
        xy: Two-character status code (e.g., "M ", " M", "??")
        path: File path
    """

    xy: str
    path: str

    @property
    def is_staged(self) -> bool:
        """True if file has staged changes."""
        return self.xy != "??" and self.xy[0] != " "

    @property
    def is_unstaged(self) -> bool:
        """True if file has unstaged changes."""
        return self.xy != "??" and self.xy[1] != " "

    @property
    def is_untracked(self) -> bool:
        """True if file is untracked."""
        return self.xy == "??"

    def pretty_xy(self) -> str:
        """Format XY with dots for spaces (". M" instead of " M")."""
        return self.xy.replace(" ", ".")


@dataclass(frozen=True, slots=True)
class GitStatus:
    """Parsed git status.

    Represents the complete status of a git repository including
    branch info, divergence from upstream, and working tree state.

    Attributes:
        branch: Current branch name
        upstream: Upstream branch (e.g., "origin/main"), None if not set
        ahead: Number of commits ahead of upstream
        behind: Number of commits behind upstream
        entries: All status entries (staged, unstaged, untracked)
    """

    branch: str
    upstream: str | None = None
    ahead: int = 0
    behind: int = 0
    entries: tuple[StatusEntry, ...] = field(default_factory=tuple)

    @property
    def is_clean(self) -> bool:
        """True if working tree has no changes."""
        return len(self.entries) == 0

    @property
    def has_divergence(self) -> bool:
        """True if branch has diverged from upstream or has no upstream."""
        return bool(self.ahead or self.behind or self.upstream is None)

    @property
    def staged(self) -> list[StatusEntry]:
        """Entries with staged changes."""
        return [e for e in self.entries if e.is_staged]

    @property
    def unstaged(self) -> list[StatusEntry]:
        """Entries with unstaged changes."""
        return [e for e in self.entries if e.is_unstaged]

    @property
    def untracked(self) -> list[StatusEntry]:
        """Untracked files."""
        return [e for e in self.entries if e.is_untracked]

    @property
    def staged_count(self) -> int:
        """Number of staged files."""
        return len(self.staged)

    @property
    def unstaged_count(self) -> int:
        """Number of unstaged files."""
        return len(self.unstaged)

    @property
    def untracked_count(self) -> int:
        """Number of untracked files."""
        return len(self.untracked)


class Repository:
    """Git repository abstraction.

    Provides methods for common git operations on a single repository.
    All methods that can fail return Result types.

    Attributes:
        path: Path to the repository root
    """

    def __init__(self, path: Path) -> None:
        """Initialize repository.

        Args:
            path: Path to repository root (containing .git)
        """
        self.path = path

    def exists(self) -> bool:
        """Check if this is a valid git repository."""
        return (self.path / ".git").exists() or (self.path / ".git").is_file()

    def status(self) -> Result[GitStatus, GitError]:
        """Get repository status.

        Runs `git status --porcelain=v1 -b` and parses the output.

        Returns:
            Ok(GitStatus) on success
            Err(GitError) on failure
        """
        result = self._run(["status", "--porcelain=v1", "-b"])
        match result:
            case Err(e):
                return Err(
                    GitError(
                        command="status",
                        message=e.stderr.strip() or "git status failed",
                        returncode=e.returncode,
                    )
                )
            case Ok(stdout):
                return Ok(self._parse_status(stdout))

    def is_clean(self) -> bool:
        """Check if working tree is clean (no changes).

        Returns False if status cannot be determined.
        """
        result = self._run(["status", "--porcelain"])
        match result:
            case Ok(stdout):
                return stdout.strip() == ""
            case Err(_):
                return False

    def has_upstream(self) -> bool:
        """Check if current branch has an upstream configured."""
        result = self._run(
            [
                "rev-parse",
                "--abbrev-ref",
                "--symbolic-full-name",
                "@{u}",
            ]
        )
        return isinstance(result, Ok)

    def current_branch(self) -> str | None:
        """Get current branch name.

        Returns None if detached HEAD or error.
        """
        result = self._run(["rev-parse", "--abbrev-ref", "HEAD"])
        match result:
            case Ok(stdout):
                branch = stdout.strip()
                return None if branch == "HEAD" else branch
            case Err(_):
                return None

    def pull_ff(self) -> Result[str, GitError]:
        """Pull with fast-forward only.

        Returns:
            Ok(output) on success
            Err(GitError) on failure (conflicts, no upstream, etc.)
        """
        result = self._run(["pull", "--ff-only"])
        match result:
            case Err(e):
                return Err(
                    GitError(
                        command="pull --ff-only",
                        message=e.stderr.strip() or e.stdout.strip() or "pull failed",
                        returncode=e.returncode,
                    )
                )
            case Ok(stdout):
                return Ok(stdout.strip())

    def fetch(self) -> Result[str, GitError]:
        """Fetch from remote.

        Returns:
            Ok(output) on success
            Err(GitError) on failure
        """
        result = self._run(["fetch"])
        match result:
            case Err(e):
                return Err(
                    GitError(
                        command="fetch",
                        message=e.stderr.strip() or "fetch failed",
                        returncode=e.returncode,
                    )
                )
            case Ok(stdout):
                return Ok(stdout.strip())

    def _run(self, args: list[str]) -> Result[str, ProcessError]:
        """Run a git command in this repository."""
        command = args[0] if args else ""
        timeout = (
            _GIT_NETWORK_TIMEOUT_SECONDS
            if command in {"fetch", "pull", "push", "clone"}
            else _GIT_TIMEOUT_SECONDS
        )
        return run_process(["git", "-C", str(self.path), *args], cwd=self.path, timeout=timeout)

    def _parse_status(self, output: str) -> GitStatus:
        """Parse git status --porcelain=v1 -b output."""
        lines = [ln for ln in output.splitlines() if ln.strip()]

        if not lines:
            return GitStatus(branch="")

        # First line is branch info: ## branch...upstream [ahead N, behind M]
        branch_line = lines[0]
        branch, upstream = self._parse_branch_line(branch_line)
        ahead, behind = self._parse_ahead_behind(branch_line)

        # Remaining lines are file entries
        entries: list[StatusEntry] = []
        for line in lines[1:]:
            entry = self._parse_entry(line)
            if entry:
                entries.append(entry)

        return GitStatus(
            branch=branch,
            upstream=upstream,
            ahead=ahead,
            behind=behind,
            entries=tuple(entries),
        )

    def _parse_branch_line(self, line: str) -> tuple[str, str | None]:
        """Parse branch line: ## branch...upstream [info]"""
        s = line.strip()
        if s.startswith("##"):
            s = s[2:].lstrip()

        # Remove [ahead N, behind M] suffix
        s = s.split(" [", 1)[0].strip()

        # Split branch...upstream
        if "..." in s:
            left, right = s.split("...", 1)
            return (left.strip(), right.strip())

        return (s, None)

    def _parse_ahead_behind(self, line: str) -> tuple[int, int]:
        """Extract ahead/behind counts from branch line."""
        ahead = 0
        behind = 0

        match = re.search(r"\[([^\]]+)\]", line)
        if not match:
            return (0, 0)

        inside = match.group(1)

        ahead_match = re.search(r"ahead\s+(\d+)", inside)
        behind_match = re.search(r"behind\s+(\d+)", inside)

        if ahead_match:
            ahead = int(ahead_match.group(1))
        if behind_match:
            behind = int(behind_match.group(1))

        return (ahead, behind)

    def _parse_entry(self, line: str) -> StatusEntry | None:
        """Parse a single status entry line."""
        if len(line) < 4:
            return None

        # Format: XY path or XY "path with spaces"
        # For untracked: ?? path
        if line.startswith("?? "):
            return StatusEntry(xy="??", path=line[3:])

        xy = line[:2]
        path = line[3:]

        return StatusEntry(xy=xy, path=path)
