from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path

from ms.cli.release_fsm import FINISH, StepHandler, StepOutcome, advance, run_state_machine
from ms.cli.release_guided_common import (
    bootstrap_app_session,
    notes_step_selector,
    preflight_with_permission,
    print_notes_status,
    save_app_state,
    select_bump,
    select_channel,
    select_green_commit,
)
from ms.cli.selector import SelectorOption, confirm_yn, select_one
from ms.core.result import Err, Ok, Result
from ms.output.console import ConsoleProtocol, Style
from ms.services.release import config
from ms.services.release.errors import ReleaseError
from ms.services.release.model import PinnedRepo, ReleaseRepo
from ms.services.release.service import (
    ensure_app_release_permissions,
    ensure_ci_green,
    plan_app_release,
    prepare_app_pr,
    publish_app_release,
)
from ms.services.release.wizard_session import (
    AppReleaseSession,
    clear_app_session,
)


@dataclass(frozen=True, slots=True)
class _AppCtx:
    workspace_root: Path
    console: ConsoleProtocol
    watch: bool
    dry_run: bool


def _app_repo(ref: str) -> ReleaseRepo:
    base = config.APP_RELEASE_REPO
    return ReleaseRepo(
        id=base.id,
        slug=base.slug,
        ref=ref,
        required_ci_workflow_file=base.required_ci_workflow_file,
    )


def _pinned(session: AppReleaseSession) -> Result[tuple[PinnedRepo, ...], ReleaseError]:
    if session.repo_sha is None:
        return Err(ReleaseError(kind="invalid_input", message="missing selected app source sha"))
    return Ok((PinnedRepo(repo=_app_repo(session.repo_ref), sha=session.repo_sha),))


def _notes_step(session: AppReleaseSession) -> Result[AppReleaseSession, ReleaseError]:
    choice = notes_step_selector(
        has_notes=session.notes_markdown is not None,
        notes_path=session.notes_path,
        title="Release Notes",
        subtitle="External notes are optional and prepended above auto-notes",
        clear_detail="Publish release with automatic notes only",
    )
    if choice.action == "cancel":
        return Err(ReleaseError(kind="invalid_input", message="release cancelled"))
    if choice.action == "back":
        return Ok(replace(session, step="summary", return_to_summary=False))
    if choice.value == "clear":
        return Ok(
            replace(
                session,
                notes_path=None,
                notes_markdown=None,
                notes_sha256=None,
                step="summary",
                return_to_summary=False,
            )
        )
    return Ok(replace(session, step="summary", return_to_summary=False))


def _step_product(s: AppReleaseSession) -> Result[StepOutcome[AppReleaseSession], ReleaseError]:
    return Ok(advance(replace(s, step="channel")))


def _step_channel(s: AppReleaseSession) -> Result[StepOutcome[AppReleaseSession], ReleaseError]:
    choice = select_channel(
        title="Release Channel",
        subtitle="Choose app release channel",
        initial_index=s.idx_channel,
        allow_back=True,
    )
    if choice.action == "cancel":
        return Err(ReleaseError(kind="invalid_input", message="release cancelled"))
    if choice.action == "back":
        return Ok(FINISH)
    assert choice.value is not None
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
    choice = select_bump(
        title="Version Bump",
        subtitle="Choose semantic version bump",
        initial_index=s.idx_bump,
        allow_back=True,
    )
    if choice.action == "cancel":
        return Err(ReleaseError(kind="invalid_input", message="release cancelled"))
    if choice.action == "back":
        return Ok(advance(replace(s, step="channel")))
    assert choice.value is not None
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


def _step_sha(
    s: AppReleaseSession, *, ctx: _AppCtx
) -> Result[StepOutcome[AppReleaseSession], ReleaseError]:
    commit = select_green_commit(
        workspace_root=ctx.workspace_root,
        repo_slug=config.APP_REPO_SLUG,
        ref=s.repo_ref,
        workflow_file=config.APP_RELEASE_REPO.required_ci_workflow_file,
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
    assert choice.value is not None
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


def _step_tag(
    s: AppReleaseSession, *, ctx: _AppCtx
) -> Result[StepOutcome[AppReleaseSession], ReleaseError]:
    if s.channel is None or s.bump is None:
        return Err(ReleaseError(kind="invalid_input", message="missing channel/bump selection"))
    pinned = _pinned(s)
    if isinstance(pinned, Err):
        return pinned

    planned = plan_app_release(
        workspace_root=ctx.workspace_root,
        channel=s.channel,
        bump=s.bump,
        tag_override=None,
        pinned=pinned.value,
    )
    if isinstance(planned, Err):
        return planned
    tag, version = planned.value

    choice = select_one(
        title="Release Tag",
        subtitle="Tag is generated from channel + bump",
        options=[SelectorOption(value="accept", label=f"Use {tag}", detail=f"version {version}")],
        initial_index=0,
        allow_back=True,
    )
    if choice.action == "cancel":
        return Err(ReleaseError(kind="invalid_input", message="release cancelled"))
    if choice.action == "back":
        return Ok(advance(replace(s, step="sha")))
    return Ok(
        advance(replace(s, tag=tag, version=version, step="summary", return_to_summary=False))
    )


def _step_summary(s: AppReleaseSession) -> Result[StepOutcome[AppReleaseSession], ReleaseError]:
    notes_label = s.notes_path or "none"
    options = [
        SelectorOption(value="channel", label=f"Channel: {s.channel}", detail="Edit channel"),
        SelectorOption(value="bump", label=f"Bump: {s.bump}", detail="Edit semantic bump"),
        SelectorOption(
            value="sha",
            label=f"Source SHA: {(s.repo_sha or 'unset')[:12]}",
            detail="Edit selected source commit",
        ),
        SelectorOption(value="tag", label=f"Tag: {s.tag}", detail=f"Version: {s.version}"),
        SelectorOption(
            value="notes", label=f"Notes file: {notes_label}", detail="Optional attached notes"
        ),
        SelectorOption(
            value="start", label="Start release", detail="Continue to final confirmation"
        ),
    ]
    choice = select_one(
        title="App Release Summary",
        subtitle="Select an item to edit, or start release",
        options=options,
        initial_index=s.idx_summary,
        allow_back=True,
    )
    if choice.action == "cancel":
        return Err(ReleaseError(kind="invalid_input", message="release cancelled"))
    if choice.action == "back":
        return Ok(advance(replace(s, step="tag")))

    assert choice.value is not None
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


def _validate_app_confirm_inputs(
    session: AppReleaseSession,
) -> Result[tuple[str, str, str], ReleaseError]:
    if session.tag is None or session.version is None or session.repo_sha is None:
        return Err(
            ReleaseError(
                kind="invalid_input",
                message="incomplete release session; missing tag/version/source sha",
            )
        )
    return Ok((session.tag, session.version, session.repo_sha))


def _dispatch_app_release(
    *,
    ctx: _AppCtx,
    session: AppReleaseSession,
    pinned: tuple[PinnedRepo, ...],
    tag: str,
    version: str,
    repo_sha: str,
) -> Result[None, ReleaseError]:
    prepared = prepare_app_pr(
        workspace_root=ctx.workspace_root,
        console=ctx.console,
        tag=tag,
        version=version,
        base_sha=repo_sha,
        pinned=pinned,
        dry_run=ctx.dry_run,
    )
    if isinstance(prepared, Err):
        return prepared

    ctx.console.success(f"PR merged: {prepared.value.pr_url}")
    ctx.console.print(f"source sha: {prepared.value.source_sha}", Style.DIM)
    print_notes_status(
        console=ctx.console,
        notes_markdown=session.notes_markdown,
        notes_path=session.notes_path,
        notes_sha256=session.notes_sha256,
        auto_label="notes: automatic notes only",
    )

    run = publish_app_release(
        workspace_root=ctx.workspace_root,
        console=ctx.console,
        tag=tag,
        source_sha=prepared.value.source_sha,
        notes_markdown=session.notes_markdown,
        notes_source_path=session.notes_path,
        watch=ctx.watch,
        dry_run=ctx.dry_run,
    )
    if isinstance(run, Err):
        return run

    candidate_url, release_url = run.value
    ctx.console.success(f"Candidate run: {candidate_url}")
    ctx.console.success(f"Release run: {release_url}")
    ctx.console.print(
        "Next: approve the 'app-release' environment in GitHub Actions to publish.",
        Style.DIM,
    )

    cleared = clear_app_session(workspace_root=ctx.workspace_root)
    if isinstance(cleared, Err):
        return cleared
    return Ok(None)


def _step_confirm(
    s: AppReleaseSession, *, ctx: _AppCtx
) -> Result[StepOutcome[AppReleaseSession], ReleaseError]:
    approved = confirm_yn(
        prompt=f"Publish {s.tag} from {s.repo_sha[:12] if s.repo_sha else 'unset'}"
    )
    if not approved:
        return Ok(advance(replace(s, step="summary")))

    pinned = _pinned(s)
    if isinstance(pinned, Err):
        return pinned

    green = ensure_ci_green(
        workspace_root=ctx.workspace_root,
        pinned=pinned.value,
        allow_non_green=False,
    )
    if isinstance(green, Err):
        return green

    valid = _validate_app_confirm_inputs(s)
    if isinstance(valid, Err):
        return valid
    tag, version, repo_sha = valid.value

    dispatched = _dispatch_app_release(
        ctx=ctx,
        session=s,
        pinned=pinned.value,
        tag=tag,
        version=version,
        repo_sha=repo_sha,
    )
    if isinstance(dispatched, Err):
        return dispatched

    return Ok(FINISH)


def _handlers(*, ctx: _AppCtx) -> dict[str, StepHandler[AppReleaseSession]]:
    return {
        "product": _step_product,
        "channel": _step_channel,
        "bump": _step_bump,
        "sha": lambda s: _step_sha(s, ctx=ctx),
        "tag": lambda s: _step_tag(s, ctx=ctx),
        "summary": _step_summary,
        "notes": _step_notes,
        "confirm": lambda s: _step_confirm(s, ctx=ctx),
    }


def run_guided_app_release(
    *,
    workspace_root: Path,
    console: ConsoleProtocol,
    notes_file: Path | None,
    watch: bool,
    dry_run: bool,
) -> Result[None, ReleaseError]:
    preflight = preflight_with_permission(
        workspace_root=workspace_root,
        console=console,
        permission_check=ensure_app_release_permissions,
    )
    if isinstance(preflight, Err):
        return preflight

    boot = bootstrap_app_session(
        workspace_root=workspace_root,
        created_by=preflight.value,
        notes_file=notes_file,
    )
    if isinstance(boot, Err):
        return boot

    saved = save_app_state(workspace_root=workspace_root, session=boot.value)
    if isinstance(saved, Err):
        return saved

    ctx = _AppCtx(
        workspace_root=workspace_root,
        console=console,
        watch=watch,
        dry_run=dry_run,
    )
    return run_state_machine(
        initial_state=saved.value,
        get_step=lambda s: s.step,
        handlers=_handlers(ctx=ctx),
        save_state=lambda s: save_app_state(workspace_root=workspace_root, session=s),
    )
