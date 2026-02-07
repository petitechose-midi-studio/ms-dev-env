from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from ms.core.result import Err, Ok, Result
from ms.output.console import ConsoleProtocol
from ms.release.domain.models import PinnedRepo, ReleasePlan
from ms.release.errors import ReleaseError


@dataclass(frozen=True, slots=True)
class PreparedContentRelease:
    plan: ReleasePlan
    pr_url: str


def prepare_content_release_distribution(
    *,
    ensure_ci_green_fn: Callable[..., Result[None, ReleaseError]],
    prepare_distribution_pr_fn: Callable[..., Result[str, ReleaseError]],
    workspace_root: Path,
    console: ConsoleProtocol,
    plan: ReleasePlan,
    pinned: tuple[PinnedRepo, ...],
    notes: str | None,
    notes_file: Path | None,
    allow_non_green: bool,
    dry_run: bool,
) -> Result[PreparedContentRelease, ReleaseError]:
    green = ensure_ci_green_fn(
        workspace_root=workspace_root,
        pinned=pinned,
        allow_non_green=allow_non_green,
    )
    if isinstance(green, Err):
        return green

    pr = prepare_distribution_pr_fn(
        workspace_root=workspace_root,
        console=console,
        plan=plan,
        user_notes=notes,
        user_notes_file=notes_file,
        dry_run=dry_run,
    )
    if isinstance(pr, Err):
        return pr

    return Ok(PreparedContentRelease(plan=plan, pr_url=pr.value))
