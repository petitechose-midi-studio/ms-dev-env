from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


ReleaseChannel = Literal["stable", "beta"]
ReleaseBump = Literal["major", "minor", "patch"]


@dataclass(frozen=True, slots=True)
class ReleaseRepo:
    """A repo that is pinned into a release spec."""

    id: str
    slug: str  # owner/name
    ref: str
    # Optional: some repos have no CI gating yet.
    required_ci_workflow_file: str | None


@dataclass(frozen=True, slots=True)
class RepoCommit:
    sha: str
    message: str
    date_utc: str | None

    @property
    def short_sha(self) -> str:
        return self.sha[:8]


@dataclass(frozen=True, slots=True)
class PinnedRepo:
    repo: ReleaseRepo
    sha: str


@dataclass(frozen=True, slots=True)
class ReleasePlan:
    channel: ReleaseChannel
    tag: str
    pinned: tuple[PinnedRepo, ...]
    spec_path: str
    notes_path: str | None
    title: str


@dataclass(frozen=True, slots=True)
class DistributionRelease:
    tag: str
    prerelease: bool
