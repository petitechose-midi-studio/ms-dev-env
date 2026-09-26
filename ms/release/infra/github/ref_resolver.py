"""GitHub ref resolution shared by release flows."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from ms.core.result import Result
from ms.release.errors import ReleaseError
from ms.release.infra.github.client import get_ref_head_sha

RefResolver = Callable[[str, str], Result[str, ReleaseError]]


def github_ref_resolver(*, workspace_root: Path) -> RefResolver:
    """Resolve a repo ref to its head SHA via gh."""

    def resolve(repo: str, ref: str) -> Result[str, ReleaseError]:
        return get_ref_head_sha(workspace_root=workspace_root, repo=repo, ref=ref)

    return resolve
