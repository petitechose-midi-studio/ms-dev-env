from __future__ import annotations

from pathlib import Path
from typing import Literal

from ms.core.result import Err, Ok, Result
from ms.output.console import ConsoleProtocol, Style
from ms.release.domain.models import PinnedRepo, ReleasePlan
from ms.release.errors import ReleaseError

from .content_contracts import ContentGuidedDependencies
from .sessions import ContentReleaseSession


def ensure_open_control_clean(
    *,
    deps: ContentGuidedDependencies,
    workspace_root: Path,
    pinned: tuple[PinnedRepo, ...],
) -> Result[None, ReleaseError]:
    core_pin = next((pin for pin in pinned if pin.repo.id == "core"), None)
    if core_pin is None:
        return Ok(None)

    preflight_oc = deps.preflight_open_control(workspace_root=workspace_root, core_sha=core_pin.sha)
    if preflight_oc.dirty_repos():
        return Err(
            ReleaseError(
                kind="invalid_input",
                message=(
                    "open-control has uncommitted changes "
                    "(release builds may differ from dev symlink)"
                ),
            )
        )
    return Ok(None)


def validate_content_confirm_inputs(
    session: ContentReleaseSession,
) -> Result[
    tuple[Literal["stable", "beta"], Literal["major", "minor", "patch"], str], ReleaseError
]:
    if session.channel is None or session.bump is None or session.tag is None:
        return Err(
            ReleaseError(
                kind="invalid_input",
                message="incomplete content release session; missing channel/bump/tag",
            )
        )
    return Ok((session.channel, session.bump, session.tag))


def dispatch_content_release(
    *,
    deps: ContentGuidedDependencies,
    workspace_root: Path,
    console: ConsoleProtocol,
    watch: bool,
    dry_run: bool,
    session: ContentReleaseSession,
    plan: ReleasePlan,
) -> Result[None, ReleaseError]:
    deps.print_notes_status(
        console=console,
        notes_markdown=session.notes_markdown,
        notes_path=session.notes_path,
        notes_sha256=session.notes_sha256,
        auto_label="notes: automatic notes only",
    )

    candidates = deps.ensure_content_candidates(
        workspace_root=workspace_root,
        console=console,
        plan=plan,
        dry_run=dry_run,
    )
    if isinstance(candidates, Err):
        return candidates

    pr = deps.prepare_distribution_pr(
        workspace_root=workspace_root,
        console=console,
        plan=plan,
        user_notes=session.notes_markdown,
        user_notes_file=None,
        dry_run=dry_run,
    )
    if isinstance(pr, Err):
        return pr

    console.success(f"PR merged: {pr.value}")

    run = deps.publish_distribution_release(
        workspace_root=workspace_root,
        console=console,
        plan=plan,
        watch=watch,
        dry_run=dry_run,
    )
    if isinstance(run, Err):
        return run

    console.success(f"Workflow run: {run.value}")
    console.print(
        "Next: approve the 'release' environment in GitHub Actions to sign + publish.",
        Style.DIM,
    )

    cleared = deps.clear_session()
    if isinstance(cleared, Err):
        return cleared
    return Ok(None)
