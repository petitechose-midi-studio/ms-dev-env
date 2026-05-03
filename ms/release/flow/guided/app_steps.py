from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from ms.core.result import Err, Ok, Result
from ms.output.console import ConsoleProtocol
from ms.release.domain.models import PinnedRepo, ReleaseRepo
from ms.release.errors import ReleaseError

from .app_confirm_step import refresh_app_session_tooling, run_app_confirm_step
from .app_contracts import AppGuidedDependencies, AppPrepareResultLike
from .app_notes_step import run_app_notes_step
from .app_pins import pinned_app_repo
from .app_summary_options import build_app_summary_options
from .fsm import FINISH, StepHandler, StepOutcome, advance, run_state_machine
from .menu_option import MenuOption
from .sessions import AppReleaseSession


def run_guided_app_release_flow[PrepareT: AppPrepareResultLike](
    *,
    workspace_root: Path,
    console: ConsoleProtocol,
    notes_file: Path | None,
    watch: bool,
    dry_run: bool,
    app_repo_slug: str,
    app_release_repo: ReleaseRepo,
    deps: AppGuidedDependencies[PrepareT],
) -> Result[None, ReleaseError]:
    def _pinned(session: AppReleaseSession) -> Result[tuple[PinnedRepo, ...], ReleaseError]:
        return pinned_app_repo(app_release_repo=app_release_repo, session=session)

    def _notes_step(session: AppReleaseSession) -> Result[AppReleaseSession, ReleaseError]:
        return run_app_notes_step(deps=deps, session=session)

    def _step_product(s: AppReleaseSession) -> Result[StepOutcome[AppReleaseSession], ReleaseError]:
        return Ok(advance(replace(s, step="channel")))

    def _step_channel(s: AppReleaseSession) -> Result[StepOutcome[AppReleaseSession], ReleaseError]:
        choice = deps.select_channel(
            title="Release Channel",
            subtitle="Choose app release channel",
            initial_index=s.idx_channel,
            allow_back=True,
        )
        if choice.action == "cancel":
            return Err(ReleaseError(kind="invalid_input", message="release cancelled"))
        if choice.action == "back":
            return Ok(FINISH)
        if choice.value is None:
            return Err(ReleaseError(kind="invalid_input", message="missing channel selection"))
        return Ok(
            advance(
                replace(
                    s,
                    channel=choice.value,
                    tag=None,
                    version=None,
                    idx_channel=choice.index,
                    step=("summary" if s.return_to_summary else "bump"),
                    return_to_summary=False,
                )
            )
        )

    def _step_bump(s: AppReleaseSession) -> Result[StepOutcome[AppReleaseSession], ReleaseError]:
        choice = deps.select_bump(
            title="Version Bump",
            subtitle="Choose semantic version bump",
            initial_index=s.idx_bump,
            allow_back=True,
        )
        if choice.action == "cancel":
            return Err(ReleaseError(kind="invalid_input", message="release cancelled"))
        if choice.action == "back":
            return Ok(advance(replace(s, step="channel")))
        if choice.value is None:
            return Err(ReleaseError(kind="invalid_input", message="missing bump selection"))
        return Ok(
            advance(
                replace(
                    s,
                    bump=choice.value,
                    tag=None,
                    version=None,
                    idx_bump=choice.index,
                    step=("summary" if s.return_to_summary else "sha"),
                    return_to_summary=False,
                )
            )
        )

    def _step_sha(s: AppReleaseSession) -> Result[StepOutcome[AppReleaseSession], ReleaseError]:
        commit = deps.select_green_commit(
            workspace_root=workspace_root,
            repo_slug=app_repo_slug,
            ref=s.repo_ref,
            workflow_file=app_release_repo.required_ci_workflow_file,
            title="Source Commit",
            subtitle="Pick CI-green commit",
            current_sha=s.repo_sha,
            initial_index=s.idx_sha,
            allow_back=True,
        )
        if isinstance(commit, Err):
            return commit
        choice = commit.value
        if choice.action == "cancel":
            return Err(ReleaseError(kind="invalid_input", message="release cancelled"))
        if choice.action == "back":
            return Ok(advance(replace(s, step="bump")))
        if choice.value is None:
            return Err(ReleaseError(kind="invalid_input", message="missing source sha selection"))
        return Ok(
            advance(
                replace(
                    s,
                    repo_sha=choice.value,
                    tag=None,
                    version=None,
                    idx_sha=choice.index,
                    step=("summary" if s.return_to_summary else "tag"),
                    return_to_summary=False,
                )
            )
        )

    def _step_tag(s: AppReleaseSession) -> Result[StepOutcome[AppReleaseSession], ReleaseError]:
        if s.channel is None or s.bump is None:
            return Err(ReleaseError(kind="invalid_input", message="missing channel/bump selection"))
        pinned = _pinned(s)
        if isinstance(pinned, Err):
            return pinned

        planned = deps.plan_app_release(
            workspace_root=workspace_root,
            channel=s.channel,
            bump=s.bump,
            tag_override=None,
            pinned=pinned.value,
        )
        if isinstance(planned, Err):
            return planned
        plan = planned.value
        tag = plan.tag
        version = plan.version

        choice = deps.select_menu(
            title="Release Tag",
            subtitle="Tag is generated from channel + bump",
            options=[MenuOption(value="accept", label=f"Use {tag}", detail=f"version {version}")],
            initial_index=0,
            allow_back=True,
        )
        if choice.action == "cancel":
            return Err(ReleaseError(kind="invalid_input", message="release cancelled"))
        if choice.action == "back":
            return Ok(advance(replace(s, step="sha")))
        return Ok(
            advance(
                replace(
                    s,
                    tag=tag,
                    version=version,
                    tooling_sha=plan.tooling.sha,
                    step="summary",
                    return_to_summary=False,
                )
            )
        )

    def _step_summary(s: AppReleaseSession) -> Result[StepOutcome[AppReleaseSession], ReleaseError]:
        choice = deps.select_menu(
            title="App Release Summary",
            subtitle="Select an item to edit, or start release",
            options=build_app_summary_options(s),
            initial_index=s.idx_summary,
            allow_back=True,
        )
        if choice.action == "cancel":
            return Err(ReleaseError(kind="invalid_input", message="release cancelled"))
        if choice.action == "back":
            return Ok(advance(replace(s, step="tag")))
        if choice.value is None:
            return Err(ReleaseError(kind="invalid_input", message="missing summary action"))

        next_step = "confirm" if choice.value == "start" and s.tag is not None else "tag"
        if choice.value in {"channel", "bump", "sha", "tag", "notes"}:
            next_step = choice.value
        return Ok(
            advance(
                replace(
                    s,
                    idx_summary=choice.index,
                    step=next_step,
                    return_to_summary=(
                        choice.value in {"channel", "bump", "sha", "tag", "notes", "start"}
                        and next_step != "confirm"
                    ),
                )
            )
        )

    def _step_notes(s: AppReleaseSession) -> Result[StepOutcome[AppReleaseSession], ReleaseError]:
        next_s = _notes_step(s)
        if isinstance(next_s, Err):
            return next_s
        return Ok(advance(next_s.value))

    def _step_confirm(
        s: AppReleaseSession,
    ) -> Result[StepOutcome[AppReleaseSession], ReleaseError]:
        return run_app_confirm_step(
            session=s,
            workspace_root=workspace_root,
            console=console,
            app_release_repo=app_release_repo,
            deps=deps,
            watch=watch,
            dry_run=dry_run,
        )

    def _handlers() -> dict[str, StepHandler[AppReleaseSession]]:
        return {
            "product": _step_product,
            "channel": _step_channel,
            "bump": _step_bump,
            "sha": _step_sha,
            "tag": _step_tag,
            "summary": _step_summary,
            "notes": _step_notes,
            "confirm": _step_confirm,
        }

    preflight = deps.preflight()
    if isinstance(preflight, Err):
        return preflight

    boot = deps.bootstrap_session(created_by=preflight.value, notes_file=notes_file)
    if isinstance(boot, Err):
        return boot

    current = refresh_app_session_tooling(
        session=boot.value,
        workspace_root=workspace_root,
        console=console,
    )
    if isinstance(current, Err):
        return current

    saved = deps.save_state(session=current.value)
    if isinstance(saved, Err):
        return saved

    return run_state_machine(
        initial_state=saved.value,
        get_step=lambda s: s.step,
        handlers=_handlers(),
        save_state=lambda s: deps.save_state(session=s),
    )
