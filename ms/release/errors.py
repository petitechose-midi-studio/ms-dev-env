"""Error types for the release bounded context."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True, slots=True)
class ReleaseError:
    """Canonical release error payload."""

    kind: Literal[
        "gh_missing",
        "gh_auth_required",
        "permission_denied",
        "invalid_input",
        "artifact_missing",
        "invalid_tag",
        "tag_exists",
        "ci_not_green",
        "repo_dirty",
        "repo_failed",
        "workflow_failed",
        "verification_failed",
    ]
    message: str
    hint: str | None = None

    def pretty(self) -> str:
        if self.hint:
            return f"{self.message} (hint: {self.hint})"
        return self.message


__all__ = ["ReleaseError"]
