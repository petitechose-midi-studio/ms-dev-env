from __future__ import annotations

from pathlib import Path

from ms.core.result import Err, Ok, Result
from ms.release.errors import ReleaseError
from ms.release.infra.github.client import get_ref_head_sha


def is_commit_fetchable(
    *, workspace_root: Path, repo: str, sha: str
) -> Result[bool, ReleaseError]:
    resolved = get_ref_head_sha(workspace_root=workspace_root, repo=repo, ref=sha)
    if isinstance(resolved, Err):
        return Err(resolved.error)
    return Ok(resolved.value == sha)
