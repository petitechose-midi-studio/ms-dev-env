from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

from ms.core.result import Err, Ok, Result
from ms.output.console import ConsoleProtocol
from ms.release.domain import config
from ms.release.domain.models import ReleaseRepo
from ms.release.errors import ReleaseError
from ms.release.flow.remote_coherence import assert_release_remote_coherence
from ms.release.infra.github.workflows import dispatch_publish_request_id

from .content_bom_step import assess_content_bom
from .content_contracts import ContentConfirmationDependencies
from .content_plan_state import resolve_content_release_plan
from .content_release_dispatch import (
    ensure_open_control_clean,
    prepare_content_release,
    publish_prepared_content_release,
)
from .fsm import FINISH, StepOutcome, advance
from .menu_option import MenuOption
from .pending_op import reconcile_pending_op
from .sessions import ContentReleaseSession


def run_content_confirm_step(
    *,
    deps: ContentConfirmationDependencies,
    workspace_root: Path,
    console: ConsoleProtocol,
    watch: bool,
    dry_run: bool,
    session: ContentReleaseSession,
    release_repos: tuple[ReleaseRepo, ...],
) -> Result[StepOutcome[ContentReleaseSession], ReleaseError]:
    if session.pending_kind is not None:
        return _resume_content_pending(
            session=session, workspace_root=workspace_root, deps=deps
        )

    bom = assess_content_bom(
        deps=deps,
        workspace_root=workspace_root,
        session=session,
        release_repos=release_repos,
    )
    if bom.status != "aligned":
        console.warning(f"OpenControl BOM not ready: {bom.detail}")
        return Ok(
            advance(
                replace(
                    session,
                    step="bom",
                    cursor=replace(session.cursor, return_to_summary=True),
                )
            )
        )

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

    coherence = assert_release_remote_coherence(
        workspace_root=workspace_root,
        console=console,
        pinned=planned.value.pinned,
        tooling=planned.value.tooling,
        dry_run=dry_run,
        verify_ci=False,
    )
    if isinstance(coherence, Err):
        return coherence

    effective_watch = watch
    if not watch and not dry_run:
        watch_choice = deps.select_menu(
            title="Release Watch",
            subtitle="Watch the publish workflow after dispatch?",
            options=[
                MenuOption(
                    value="watch",
                    label="Watch workflow",
                    detail="wait for the GitHub Actions run to complete",
                ),
                MenuOption(
                    value="skip",
                    label="Skip watch",
                    detail="dispatch and finish immediately",
                ),
            ],
            initial_index=0,
            allow_back=False,
        )
        if watch_choice.action == "cancel":
            return Err(ReleaseError(kind="invalid_input", message="release watch cancelled"))
        effective_watch = watch_choice.value == "watch"

    prepared = prepare_content_release(
        deps=deps,
        workspace_root=workspace_root,
        console=console,
        dry_run=dry_run,
        session=session,
        plan=planned.value,
        remote_coherence_checked=True,
    )
    if isinstance(prepared, Err):
        return prepared

    request_id: str | None = None
    if not dry_run:
        request = dispatch_publish_request_id(
            workspace_root=workspace_root,
            channel=planned.value.channel,
            tag=planned.value.tag,
            spec_path=planned.value.spec_path,
            tooling_sha=planned.value.tooling.sha,
        )
        if isinstance(request, Err):
            return request
        request_id = request.value
        marker = replace(
            session,
            pending_kind="content_release",
            pending_request_id=request_id,
            pending_repo=config.DIST_REPO_SLUG,
            pending_workflow=config.DIST_PUBLISH_WORKFLOW,
            pending_tag=planned.value.tag,
            pending_source_sha=None,
            pending_tooling_sha=planned.value.tooling.sha,
            pending_inputs=(
                ("channel", planned.value.channel),
                ("tag", planned.value.tag),
                ("spec_path", planned.value.spec_path),
                ("tooling_sha", planned.value.tooling.sha),
            ),
            pending_at=datetime.now(tz=UTC).isoformat(),
        )
        saved = deps.save_state(session=marker)
        if isinstance(saved, Err):
            return saved
        session = saved.value

    dispatched = publish_prepared_content_release(
        deps=deps,
        workspace_root=workspace_root,
        console=console,
        watch=effective_watch,
        dry_run=dry_run,
        plan=planned.value,
        request_id=request_id,
    )
    if isinstance(dispatched, Err):
        return dispatched

    return Ok(FINISH)


def _resume_content_pending(
    *,
    session: ContentReleaseSession,
    workspace_root: Path,
    deps: ContentConfirmationDependencies,
) -> Result[StepOutcome[ContentReleaseSession], ReleaseError]:
    reconciled = reconcile_pending_op(
        workspace_root=workspace_root,
        repo=session.pending_repo or config.DIST_REPO_SLUG,
        workflow_file=session.pending_workflow or config.DIST_PUBLISH_WORKFLOW,
        tag=session.pending_tag or "",
        request_id=session.pending_request_id,
        source_sha=session.pending_source_sha,
        tooling_sha=session.pending_tooling_sha,
        inputs=session.pending_inputs,
    )
    if isinstance(reconciled, Err):
        return reconciled
    outcome = reconciled.value
    if outcome.state == "completed":
        saved = deps.clear_session()
        if isinstance(saved, Err):
            return saved
        return Ok(FINISH)
    return Err(
        ReleaseError(
            kind="workflow_failed",
            message=f"content release state unresolved ({outcome.state}): {outcome.detail}",
            hint=outcome.run_url or "Inspect GitHub before retrying.",
        )
    )
