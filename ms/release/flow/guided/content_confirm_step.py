from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from ms.core.result import Err, Ok, Result
from ms.output.console import ConsoleProtocol
from ms.release.domain.models import ReleaseRepo
from ms.release.errors import ReleaseError

from .content_bom_step import assess_content_bom
from .content_contracts import ContentGuidedDependencies
from .content_plan_state import resolve_content_release_plan
from .content_release_dispatch import (
    dispatch_content_release,
    ensure_open_control_clean,
)
from .fsm import FINISH, StepOutcome, advance
from .sessions import ContentReleaseSession


def run_content_confirm_step(
    *,
    deps: ContentGuidedDependencies,
    workspace_root: Path,
    console: ConsoleProtocol,
    watch: bool,
    dry_run: bool,
    session: ContentReleaseSession,
    release_repos: tuple[ReleaseRepo, ...],
) -> Result[StepOutcome[ContentReleaseSession], ReleaseError]:
    bom = assess_content_bom(
        deps=deps,
        workspace_root=workspace_root,
        session=session,
        release_repos=release_repos,
    )
    if bom.status != "aligned":
        console.warning(f"OpenControl BOM not ready: {bom.detail}")
        return Ok(advance(replace(session, step="bom", return_to_summary=True)))

    approved = deps.confirm(prompt=f"Publish content {session.tag or 'unset'}")
    if not approved:
        return Ok(advance(replace(session, step="summary")))

    planned = resolve_content_release_plan(
        deps=deps,
        workspace_root=workspace_root,
        session=session,
        release_repos=release_repos,
    )
    if isinstance(planned, Err):
        return planned

    green = deps.ensure_ci_green(
        workspace_root=workspace_root,
        pinned=planned.value.pinned,
        allow_non_green=False,
    )
    if isinstance(green, Err):
        return green

    clean = ensure_open_control_clean(
        deps=deps,
        workspace_root=workspace_root,
        pinned=planned.value.pinned,
    )
    if isinstance(clean, Err):
        return clean

    dispatched = dispatch_content_release(
        deps=deps,
        workspace_root=workspace_root,
        console=console,
        watch=watch,
        dry_run=dry_run,
        session=session,
        plan=planned.value,
    )
    if isinstance(dispatched, Err):
        return dispatched

    return Ok(FINISH)
