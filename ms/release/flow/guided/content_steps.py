from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from ms.core.result import Err, Ok, Result
from ms.output.console import ConsoleProtocol
from ms.release.domain.models import ReleaseRepo
from ms.release.errors import ReleaseError

from .content_bom_step import assess_content_bom, run_content_bom_step
from .content_contracts import ContentGuidedDependencies
from .content_notes_step import run_content_notes_step
from .content_release_dispatch import (
    dispatch_content_release,
    ensure_open_control_clean,
    validate_content_confirm_inputs,
)
from .content_repo_pins import pinned, set_sha, sha_map
from .content_summary_step import step_content_summary
from .fsm import FINISH, StepHandler, StepOutcome, advance, run_state_machine
from .menu_option import MenuOption
from .sessions import ContentReleaseSession


def run_guided_content_release_flow(
    *,
    workspace_root: Path,
    console: ConsoleProtocol,
    notes_file: Path | None,
    watch: bool,
    dry_run: bool,
    release_repos: tuple[ReleaseRepo, ...],
    deps: ContentGuidedDependencies,
) -> Result[None, ReleaseError]:
    def _notes_step(session: ContentReleaseSession) -> Result[ContentReleaseSession, ReleaseError]:
        return run_content_notes_step(deps=deps, session=session)

    def _step_product(
        session: ContentReleaseSession,
    ) -> Result[StepOutcome[ContentReleaseSession], ReleaseError]:
        return Ok(advance(replace(session, step="channel")))

    def _step_channel(
        session: ContentReleaseSession,
    ) -> Result[StepOutcome[ContentReleaseSession], ReleaseError]:
        choice = deps.select_channel(
            title="Content Release Channel",
            subtitle="Choose content release channel",
            initial_index=session.idx_channel,
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
                    session,
                    channel=choice.value,
                    tag=None,
                    idx_channel=choice.index,
                    step=("summary" if session.return_to_summary else "bump"),
                    return_to_summary=False,
                )
            )
        )

    def _step_bump(
        session: ContentReleaseSession,
    ) -> Result[StepOutcome[ContentReleaseSession], ReleaseError]:
        choice = deps.select_bump(
            title="Content Version Bump",
            subtitle="Choose semantic version bump",
            initial_index=session.idx_bump,
            allow_back=True,
        )
        if choice.action == "cancel":
            return Err(ReleaseError(kind="invalid_input", message="release cancelled"))
        if choice.action == "back":
            return Ok(advance(replace(session, step="channel")))
        if choice.value is None:
            return Err(ReleaseError(kind="invalid_input", message="missing bump selection"))
        return Ok(
            advance(
                replace(
                    session,
                    bump=choice.value,
                    tag=None,
                    idx_bump=choice.index,
                    repo_cursor=0,
                    step=("summary" if session.return_to_summary else "repo"),
                    return_to_summary=False,
                )
            )
        )

    def _step_repo(
        session: ContentReleaseSession,
    ) -> Result[StepOutcome[ContentReleaseSession], ReleaseError]:
        current = session
        if current.repo_cursor < 0 or current.repo_cursor >= len(release_repos):
            current = replace(current, repo_cursor=0)

        repo = release_repos[current.repo_cursor]
        current_sha = sha_map(current).get(repo.id)
        commit = deps.select_green_commit(
            workspace_root=workspace_root,
            repo_slug=repo.slug,
            ref=repo.ref,
            workflow_file=repo.required_ci_workflow_file,
            title=f"Source Commit ({repo.id})",
            subtitle=f"Pick CI-green commit for {repo.slug}",
            current_sha=current_sha,
            initial_index=current.idx_repo,
            allow_back=True,
        )
        if isinstance(commit, Err):
            return commit
        choice = commit.value
        if choice.action == "cancel":
            return Err(ReleaseError(kind="invalid_input", message="release cancelled"))
        if choice.action == "back":
            if current.return_to_summary:
                return Ok(advance(replace(current, step="summary", return_to_summary=False)))
            if current.repo_cursor == 0:
                return Ok(advance(replace(current, step="bump")))
            return Ok(advance(replace(current, repo_cursor=current.repo_cursor - 1)))

        if choice.value is None:
            return Err(ReleaseError(kind="invalid_input", message="missing repo sha selection"))
        next_session = set_sha(
            current,
            release_repos=release_repos,
            repo_id=repo.id,
            sha=choice.value,
        )
        next_session = replace(next_session, idx_repo=choice.index)
        if next_session.return_to_summary:
            return Ok(advance(replace(next_session, step="summary", return_to_summary=False)))
        if next_session.repo_cursor + 1 < len(release_repos):
            return Ok(advance(replace(next_session, repo_cursor=next_session.repo_cursor + 1)))
        return Ok(advance(replace(next_session, step="tag")))

    def _step_tag(
        session: ContentReleaseSession,
    ) -> Result[StepOutcome[ContentReleaseSession], ReleaseError]:
        if session.channel is None or session.bump is None:
            return Err(ReleaseError(kind="invalid_input", message="missing channel/bump selection"))
        pinned_repos = pinned(session, release_repos=release_repos)
        if isinstance(pinned_repos, Err):
            return pinned_repos

        planned = deps.plan_release(
            workspace_root=workspace_root,
            channel=session.channel,
            bump=session.bump,
            tag_override=None,
            pinned=pinned_repos.value,
        )
        if isinstance(planned, Err):
            return planned
        tag = planned.value.tag

        choice = deps.select_menu(
            title="Content Release Tag",
            subtitle="Tag is generated from channel + bump",
            options=[
                MenuOption(value="accept", label=f"Use {tag}", detail=planned.value.spec_path)
            ],
            initial_index=0,
            allow_back=True,
        )
        if choice.action == "cancel":
            return Err(ReleaseError(kind="invalid_input", message="release cancelled"))
        if choice.action == "back":
            return Ok(advance(replace(session, step="repo", repo_cursor=len(release_repos) - 1)))
        return Ok(advance(replace(session, tag=tag, step="summary", return_to_summary=False)))

    def _step_summary(
        session: ContentReleaseSession,
    ) -> Result[StepOutcome[ContentReleaseSession], ReleaseError]:
        return step_content_summary(
            deps=deps,
            workspace_root=workspace_root,
            session=session,
            release_repos=release_repos,
        )

    def _step_bom(
        session: ContentReleaseSession,
    ) -> Result[StepOutcome[ContentReleaseSession], ReleaseError]:
        choice = run_content_bom_step(
            deps=deps,
            workspace_root=workspace_root,
            console=console,
            dry_run=dry_run,
            session=session,
            release_repos=release_repos,
        )
        if isinstance(choice, Err):
            return choice
        if choice.value.action == "repo":
            core_index = next((idx for idx, repo in enumerate(release_repos) if repo.id == "core"), 0)
            return Ok(
                advance(
                    replace(
                        choice.value.session,
                        step="repo",
                        repo_cursor=core_index,
                        return_to_summary=True,
                    )
                )
            )
        return Ok(
            advance(
                replace(
                    choice.value.session,
                    step="summary",
                    return_to_summary=False,
                )
            )
        )

    def _step_notes(
        session: ContentReleaseSession,
    ) -> Result[StepOutcome[ContentReleaseSession], ReleaseError]:
        next_session = _notes_step(session)
        if isinstance(next_session, Err):
            return next_session
        return Ok(advance(next_session.value))

    def _step_confirm(
        session: ContentReleaseSession,
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

        pinned_repos = pinned(session, release_repos=release_repos)
        if isinstance(pinned_repos, Err):
            return pinned_repos

        green = deps.ensure_ci_green(
            workspace_root=workspace_root,
            pinned=pinned_repos.value,
            allow_non_green=False,
        )
        if isinstance(green, Err):
            return green

        clean = ensure_open_control_clean(
            deps=deps,
            workspace_root=workspace_root,
            pinned=pinned_repos.value,
        )
        if isinstance(clean, Err):
            return clean

        valid = validate_content_confirm_inputs(session)
        if isinstance(valid, Err):
            return valid
        channel, bump, tag = valid.value

        planned = deps.plan_release(
            workspace_root=workspace_root,
            channel=channel,
            bump=bump,
            tag_override=tag,
            pinned=pinned_repos.value,
        )
        if isinstance(planned, Err):
            return planned

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

    def _handlers() -> dict[str, StepHandler[ContentReleaseSession]]:
        return {
            "product": _step_product,
            "channel": _step_channel,
            "bump": _step_bump,
            "repo": _step_repo,
            "bom": _step_bom,
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

    saved = deps.save_state(session=boot.value)
    if isinstance(saved, Err):
        return saved

    return run_state_machine(
        initial_state=saved.value,
        get_step=lambda s: s.step,
        handlers=_handlers(),
        save_state=lambda s: deps.save_state(session=s),
    )
