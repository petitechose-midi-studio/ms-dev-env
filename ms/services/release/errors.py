from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True, slots=True)
class ReleaseError:
    kind: Literal[
        "gh_missing",
        "gh_auth_required",
        "permission_denied",
        "invalid_input",
        "invalid_tag",
        "tag_exists",
        "ci_not_green",
        "dist_repo_dirty",
        "dist_repo_failed",
        "workflow_failed",
    ]
    message: str
    hint: str | None = None
