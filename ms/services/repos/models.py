from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, TypedDict


@dataclass(frozen=True, slots=True)
class RepoError:
    """Error from repository sync operations."""

    kind: Literal["manifest_invalid", "sync_failed"]
    message: str
    hint: str | None = None


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


class RepoLockPayload(TypedDict):
    org: str
    name: str
    url: str
    default_branch: str | None
    head_sha: str | None
