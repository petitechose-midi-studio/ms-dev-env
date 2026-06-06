from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from ms.core.result import Err, Ok, Result
from ms.release.domain.open_control_models import (
    OPEN_CONTROL_BOM_REPOS,
    OpenControlRepoState,
)
from ms.release.errors import ReleaseError
from ms.release.infra.github.client import get_ref_head_sha

RefResolver = Callable[[str, str], Result[str, ReleaseError]]
GITHUB_BOM_REF = "main"


def collect_github_bom_state(
    *,
    workspace_root: Path,
    ref: str = GITHUB_BOM_REF,
    ref_resolver: RefResolver | None = None,
) -> Result[tuple[OpenControlRepoState, ...], ReleaseError]:
    resolver = ref_resolver or github_ref_resolver(workspace_root=workspace_root)
    states: list[OpenControlRepoState] = []
    for repo in OPEN_CONTROL_BOM_REPOS:
        slug = f"open-control/{repo}"
        resolved = resolver(slug, ref)
        if isinstance(resolved, Err):
            return resolved
        states.append(
            OpenControlRepoState(
                repo=repo,
                path=workspace_root / "open-control" / repo,
                exists=True,
                head_sha=resolved.value,
                dirty=False,
            )
        )
    return Ok(tuple(states))


def github_ref_resolver(*, workspace_root: Path) -> RefResolver:
    def resolve(repo: str, ref: str) -> Result[str, ReleaseError]:
        return get_ref_head_sha(workspace_root=workspace_root, repo=repo, ref=ref)

    return resolve
