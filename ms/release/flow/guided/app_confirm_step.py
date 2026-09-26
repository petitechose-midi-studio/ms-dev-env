from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

from ms.core.result import Err, Ok, Result
from ms.output.console import ConsoleProtocol, Style
from ms.release.domain import config
from ms.release.domain.models import ReleaseRepo
from ms.release.errors import ReleaseError
from ms.release.flow.release_tooling import resolve_release_tooling
from ms.release.flow.remote_coherence import assert_release_remote_coherence
from ms.release.infra.github.workflows import app_release_request_id

from .app_contracts import AppGuidedDependencies, AppPrepareResultLike
from .app_pins import pinned_app_repo
from .app_release_dispatch import (
    app_session_tooling,
    prepare_app_release,
    publish_prepared_app_release,
    validate_app_confirm_inputs,
)
from .fsm import FINISH, StepOutcome, advance
from .menu_option import MenuOption
from .pending_op import reconcile_pending_op
from .sessions import AppReleaseSession


def _clear_pending(session: AppReleaseSession) -> AppReleaseSession:
    return replace(
        session,
        pending_kind=None,
        pending_request_id=None,
        pending_repo=None,
        pending_workflow=None,
        pending_tag=None,
        pending_source_sha=None,
        pending_tooling_sha=None,
        pending_at=None,
    )


def refresh_app_session_tooling(
    *,
    session: AppReleaseSession,
    workspace_root: Path,
    console: ConsoleProtocol,
) -> Result[AppReleaseSession, ReleaseError]:
    if session.tooling_sha is None:
        return Ok(session)

    tooling = resolve_release_tooling(workspace_root=workspace_root)
    if isinstance(tooling, Err):
        return tooling

    if tooling.value.sha == session.tooling_sha:
        return Ok(session)

    console.print(
        f"Release tooling refreshed: {session.tooling_sha[:12]} -> {tooling.value.sha[:12]}",
        Style.DIM,
    )
    return Ok(replace(session, tooling_sha=tooling.value.sha))


def run_app_confirm_step[PrepareT: AppPrepareResultLike](
    *,
    session: AppReleaseSession,
    workspace_root: Path,
    console: ConsoleProtocol,
    watch: bool,
    dry_run: bool,
    app_release_repo: ReleaseRepo,
    deps: AppGuidedDependencies[PrepareT],
) -> Result[StepOutcome[AppReleaseSession], ReleaseError]:
    if session.pending_kind is not None:
        return _resume_pending(
            session=session, workspace_root=workspace_root, deps=deps
        )

    source = session.repo_sha[:12] if session.repo_sha else "unset"
    approved = deps.confirm(prompt=f"Publish {session.tag} from {source}")
    if not approved:
        return Ok(advance(replace(session, step="summary")))

    refreshed = refresh_app_session_tooling(
        session=session,
        workspace_root=workspace_root,
        console=console,
    )
    if isinstance(refreshed, Err):
        return refreshed
    session = refreshed.value

    pinned = pinned_app_repo(app_release_repo=app_release_repo, session=session)
    if isinstance(pinned, Err):
        return pinned

    green = deps.ensure_ci_green(
        workspace_root=workspace_root,
        pinned=pinned.value,
        allow_non_green=False,
    )
    if isinstance(green, Err):
        return green

    valid = validate_app_confirm_inputs(session)
    if isinstance(valid, Err):
        return valid
    tag, version, repo_sha, tooling_sha = valid.value

    coherence = assert_release_remote_coherence(
        workspace_root=workspace_root,
        console=console,
        pinned=pinned.value,
        tooling=app_session_tooling(tooling_sha=tooling_sha),
        dry_run=dry_run,
        verify_ci=False,
    )
    if isinstance(coherence, Err):
        return coherence

    effective_watch = watch
    if not watch and not dry_run:
        watch_choice = deps.select_menu(
            title="Release Watch",
            subtitle="Watch candidate/release workflows after dispatch?",
            options=[
                MenuOption(
                    value="watch",
                    label="Watch workflows",
                    detail="wait for GitHub Actions runs to complete",
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

    prepared = prepare_app_release(
        deps=deps,
        workspace_root=workspace_root,
        console=console,
        dry_run=dry_run,
        session=session,
        pinned=pinned.value,
        tag=tag,
        version=version,
        repo_sha=repo_sha,
        remote_coherence_checked=True,
    )
    if isinstance(prepared, Err):
        return prepared

    request_id: str | None = None
    if not dry_run:
        request = app_release_request_id(
            workspace_root=workspace_root,
            tag=tag,
            source_sha=repo_sha,
            tooling_sha=tooling_sha,
            notes_markdown=session.notes_markdown,
            notes_source_path=session.notes_path,
        )
        if isinstance(request, Err):
            return request
        request_id = request.value
        marker = replace(
            session,
            pending_kind="app_release",
            pending_request_id=request_id,
            pending_repo=config.APP_REPO_SLUG,
            pending_workflow=config.APP_RELEASE_WORKFLOW,
            pending_tag=tag,
            pending_source_sha=repo_sha,
            pending_tooling_sha=tooling_sha,
            pending_at=datetime.now(tz=UTC).isoformat(),
        )
        saved = deps.save_state(session=marker)
        if isinstance(saved, Err):
            return saved
        session = saved.value

    dispatched = publish_prepared_app_release(
        deps=deps,
        workspace_root=workspace_root,
        console=console,
        watch=effective_watch,
        dry_run=dry_run,
        session=session,
        prepared=prepared.value,
        tag=tag,
        tooling_sha=tooling_sha,
        request_id=request_id,
    )
    if isinstance(dispatched, Err):
        return dispatched

    return Ok(FINISH)


def _resume_pending[PrepareT: AppPrepareResultLike](
    *,
    session: AppReleaseSession,
    workspace_root: Path,
    deps: AppGuidedDependencies[PrepareT],
) -> Result[StepOutcome[AppReleaseSession], ReleaseError]:
    reconciled = reconcile_pending_op(
        workspace_root=workspace_root,
        repo=session.pending_repo or config.APP_REPO_SLUG,
        workflow_file=session.pending_workflow or config.APP_RELEASE_WORKFLOW,
        tag=session.pending_tag or "",
        request_id=session.pending_request_id,
        source_sha=session.pending_source_sha,
        tooling_sha=session.pending_tooling_sha,
    )
    if isinstance(reconciled, Err):
        return reconciled

    outcome = reconciled.value
    if outcome.state == "completed":
        saved = deps.save_state(session=_clear_pending(session))
        if isinstance(saved, Err):
            return saved
        return Ok(FINISH)
    if outcome.state == "in_flight":
        return Err(
            ReleaseError(
                kind="workflow_failed",
                message=f"release already dispatched and still running: {outcome.detail}",
                hint=outcome.run_url or "Wait for the run to finish, then rerun.",
            )
        )
    if outcome.state == "failed":
        return Err(
            ReleaseError(
                kind="workflow_failed",
                message=f"dispatched release workflow failed: {outcome.detail}",
                hint=outcome.run_url or "Inspect the failed run before retrying.",
            )
        )
    return Err(
        ReleaseError(
            kind="workflow_failed",
            message="release state undetermined; not retrying automatically",
            hint=outcome.detail,
        )
    )
