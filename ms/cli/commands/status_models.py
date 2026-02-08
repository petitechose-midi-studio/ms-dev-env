from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ms.git.repository import GitStatus


@dataclass(frozen=True, slots=True)
class ChangeCounts:
    """Counts of different change types."""

    modified: int = 0
    added: int = 0
    deleted: int = 0
    untracked: int = 0

    @staticmethod
    def from_status(status: GitStatus) -> ChangeCounts:
        """Extract change counters from a git status payload."""
        return ChangeCounts(
            modified=sum(1 for entry in status.entries if entry.xy[0] == "M" or entry.xy[1] == "M"),
            added=sum(1 for entry in status.entries if entry.xy[0] == "A"),
            deleted=sum(1 for entry in status.entries if entry.xy[0] == "D" or entry.xy[1] == "D"),
            untracked=status.untracked_count,
        )

    def as_parts(self) -> list[tuple[str, str]]:
        """Render non-zero counters as colorized labels."""
        parts: list[tuple[str, str]] = []
        if self.modified:
            parts.append((f"{self.modified}M", "yellow"))
        if self.added:
            parts.append((f"{self.added}A", "green"))
        if self.deleted:
            parts.append((f"{self.deleted}D", "red"))
        if self.untracked:
            parts.append((f"{self.untracked}?", "cyan"))
        return parts

    def as_string(self) -> str:
        """Serialize counters as a single space-separated string."""
        return " ".join(label for label, _ in self.as_parts())


@dataclass
class RepoStatus:
    """Status of a single repo."""

    name: str
    path: Path
    status: GitStatus | None
    error: str | None = None

    @property
    def has_changes(self) -> bool:
        if self.status is None:
            return False
        return not self.status.is_clean or self.status.ahead > 0 or self.status.behind > 0

    @property
    def counts(self) -> ChangeCounts:
        """Return change counters, defaulting to empty counts on errors."""
        if self.status is None:
            return ChangeCounts()
        return ChangeCounts.from_status(self.status)
