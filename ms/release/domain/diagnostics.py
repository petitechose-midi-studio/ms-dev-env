from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from ms.git.repository import GitStatus

from .models import ReleaseRepo


@dataclass(frozen=True, slots=True)
class RepoReadiness:
    repo: ReleaseRepo
    ref: str
    local_path: Path
    local_exists: bool
    status: GitStatus | None
    local_head_sha: str | None
    remote_head_sha: str | None
    head_green: bool | None
    error: str | None

    def is_ready(self) -> bool:
        if self.error is not None:
            return False
        if not self.local_exists:
            return False
        if self.status is None:
            return False
        if not self.status.is_clean:
            return False
        if self.status.upstream is None:
            return False
        if self.status.ahead != 0 or self.status.behind != 0:
            return False
        if self.local_head_sha is None or self.remote_head_sha is None:
            return False
        if self.local_head_sha != self.remote_head_sha:
            return False
        if self.repo.required_ci_workflow_file is None:
            return False
        return self.head_green is True


@dataclass(frozen=True, slots=True)
class AutoSuggestion:
    repo: ReleaseRepo
    from_sha: str
    to_sha: str
    kind: Literal["bump", "local"]
    reason: str
    applyable: bool
