from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from ms.core.result import Err, Ok, Result
from ms.output.console import ConsoleProtocol
from ms.release.domain.models import ReleaseRepo
from ms.release.errors import ReleaseError
from ms.release.flow.remote_coherence import assert_release_remote_coherence

from .app_contracts import AppGuidedDependencies, AppPrepareResultLike
from .app_pins import pinned_app_repo
from .app_release_dispatch import (
    app_session_tooling,
    dispatch_app_release,
    validate_app_confirm_inputs,
)
from .fsm import FINISH, StepOutcome, advance
from .menu_option import MenuOption
from .sessions import AppReleaseSession


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
    source = session.repo_sha[:12] if session.repo_sha else "unset"
    approved = deps.confirm(prompt=f"Publish {session.tag} from {source}")
    if not approved:
        return Ok(advance(replace(session, step="summary")))

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

    dispatched = dispatch_app_release(
        deps=deps,
        workspace_root=workspace_root,
        console=console,
        watch=effective_watch,
        dry_run=dry_run,
        session=session,
        pinned=pinned.value,
        tag=tag,
        version=version,
        repo_sha=repo_sha,
        tooling_sha=tooling_sha,
        remote_coherence_checked=True,
    )
    if isinstance(dispatched, Err):
        return dispatched

    return Ok(FINISH)
