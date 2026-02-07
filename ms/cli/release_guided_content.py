from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path

from ms.cli.release_fsm import FINISH, StepHandler, StepOutcome, advance, run_state_machine
from ms.cli.release_guided_common import (
    bootstrap_content_session,
    notes_step_selector,
    preflight_with_permission,
    print_notes_status,
    save_content_state,
    select_bump,
    select_channel,
    select_green_commit,
)
from ms.cli.selector import SelectorOption, confirm_yn, select_one
from ms.core.result import Err, Ok, Result
from ms.output.console import ConsoleProtocol, Style
from ms.services.release import config
from ms.services.release.errors import ReleaseError
from ms.services.release.model import PinnedRepo, ReleaseBump, ReleaseChannel, ReleasePlan
from ms.services.release.open_control import preflight_open_control
from ms.services.release.service import (
    ensure_ci_green,
    ensure_release_permissions,
    plan_release,
    prepare_distribution_pr,
    publish_distribution_release,
)
from ms.services.release.wizard_session import (
    ContentReleaseSession,
    clear_content_session,
)


@dataclass(frozen=True, slots=True)
class _ContentCtx:
    workspace_root: Path
    console: ConsoleProtocol
    watch: bool
    dry_run: bool


def _sha_map(session: ContentReleaseSession) -> dict[str, str]:
    return {rid: sha for rid, sha in session.repo_shas}


def _set_sha(session: ContentReleaseSession, *, repo_id: str, sha: str) -> ContentReleaseSession:
    by_id = _sha_map(session)
    by_id[repo_id] = sha
    ordered = tuple((r.id, by_id[r.id]) for r in config.RELEASE_REPOS if r.id in by_id)
    return replace(session, repo_shas=ordered)


def _pinned(session: ContentReleaseSession) -> Result[tuple[PinnedRepo, ...], ReleaseError]:
    by_id = _sha_map(session)
    missing = [r.id for r in config.RELEASE_REPOS if r.id not in by_id]
    if missing:
        return Err(
            ReleaseError(
                kind="invalid_input",
                message=f"missing selected source sha for: {', '.join(missing)}",
            )
        )
    return Ok(tuple(PinnedRepo(repo=r, sha=by_id[r.id]) for r in config.RELEASE_REPOS))


def _notes_step(session: ContentReleaseSession) -> Result[ContentReleaseSession, ReleaseError]:
    choice = notes_step_selector(
        has_notes=session.notes_markdown is not None,
        notes_path=session.notes_path,
        title="Content Notes",
        subtitle="External notes are optional",
        clear_detail="Publish content release with generated notes only",
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


def _step_product(
    s: ContentReleaseSession,
) -> Result[StepOutcome[ContentReleaseSession], ReleaseError]:
    return Ok(advance(replace(s, step="channel")))


def _step_channel(
    s: ContentReleaseSession,
) -> Result[StepOutcome[ContentReleaseSession], ReleaseError]:
    choice = select_channel(
        title="Content Release Channel",
        subtitle="Choose content release channel",
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
                idx_channel=choice.index,
                step=("summary" if s.return_to_summary else "bump"),
                return_to_summary=False,
            )
        )
    )


def _step_bump(
    s: ContentReleaseSession,
) -> Result[StepOutcome[ContentReleaseSession], ReleaseError]:
    choice = select_bump(
        title="Content Version Bump",
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
                idx_bump=choice.index,
                repo_cursor=0,
                step=("summary" if s.return_to_summary else "repo"),
                return_to_summary=False,
            )
        )
    )


def _step_repo(
    s: ContentReleaseSession, *, ctx: _ContentCtx
) -> Result[StepOutcome[ContentReleaseSession], ReleaseError]:
    repos = config.RELEASE_REPOS
    current = s
    if current.repo_cursor < 0 or current.repo_cursor >= len(repos):
        current = replace(current, repo_cursor=0)

    repo = repos[current.repo_cursor]
    current_sha = _sha_map(current).get(repo.id)
    commit = select_green_commit(
        workspace_root=ctx.workspace_root,
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

    assert choice.value is not None
    next_s = _set_sha(current, repo_id=repo.id, sha=choice.value)
    next_s = replace(next_s, idx_repo=choice.index)
    if next_s.return_to_summary:
        return Ok(advance(replace(next_s, step="summary", return_to_summary=False)))
    if next_s.repo_cursor + 1 < len(repos):
        return Ok(advance(replace(next_s, repo_cursor=next_s.repo_cursor + 1)))
    return Ok(advance(replace(next_s, step="tag")))


def _step_tag(
    s: ContentReleaseSession, *, ctx: _ContentCtx
) -> Result[StepOutcome[ContentReleaseSession], ReleaseError]:
    if s.channel is None or s.bump is None:
        return Err(ReleaseError(kind="invalid_input", message="missing channel/bump selection"))
    channel = s.channel
    bump = s.bump
    pinned = _pinned(s)
    if isinstance(pinned, Err):
        return pinned

    planned = plan_release(
        workspace_root=ctx.workspace_root,
        channel=channel,
        bump=bump,
        tag_override=None,
        pinned=pinned.value,
    )
    if isinstance(planned, Err):
        return planned
    tag = planned.value.tag

    choice = select_one(
        title="Content Release Tag",
        subtitle="Tag is generated from channel + bump",
        options=[
            SelectorOption(value="accept", label=f"Use {tag}", detail=planned.value.spec_path)
        ],
        initial_index=0,
        allow_back=True,
    )
    if choice.action == "cancel":
        return Err(ReleaseError(kind="invalid_input", message="release cancelled"))
    if choice.action == "back":
        return Ok(advance(replace(s, step="repo", repo_cursor=len(config.RELEASE_REPOS) - 1)))
    return Ok(advance(replace(s, tag=tag, step="summary", return_to_summary=False)))


def _step_summary(
    s: ContentReleaseSession,
) -> Result[StepOutcome[ContentReleaseSession], ReleaseError]:
    sha_by_id = _sha_map(s)
    notes_label = s.notes_path or "none"
    options: list[SelectorOption[str]] = [
        SelectorOption(value="channel", label=f"Channel: {s.channel}", detail="Edit channel"),
        SelectorOption(value="bump", label=f"Bump: {s.bump}", detail="Edit semantic bump"),
    ]
    for i, repo in enumerate(config.RELEASE_REPOS):
        options.append(
            SelectorOption(
                value=f"repo:{i}",
                label=f"{repo.id}: {(sha_by_id.get(repo.id, 'unset'))[:12]}",
                detail=repo.slug,
            )
        )
    options.extend(
        [
            SelectorOption(value="tag", label=f"Tag: {s.tag}", detail="Computed release tag"),
            SelectorOption(
                value="notes", label=f"Notes file: {notes_label}", detail="Optional release notes"
            ),
            SelectorOption(
                value="start", label="Start release", detail="Continue to final confirmation"
            ),
        ]
    )

    choice = select_one(
        title="Content Release Summary",
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
    if choice.value == "channel":
        return Ok(
            advance(replace(s, step="channel", idx_summary=choice.index, return_to_summary=True))
        )
    if choice.value == "bump":
        return Ok(
            advance(replace(s, step="bump", idx_summary=choice.index, return_to_summary=True))
        )
    if choice.value.startswith("repo:"):
        idx = int(choice.value.split(":", 1)[1])
        return Ok(
            advance(
                replace(
                    s,
                    step="repo",
                    repo_cursor=max(0, min(idx, len(config.RELEASE_REPOS) - 1)),
                    idx_summary=choice.index,
                    return_to_summary=True,
                )
            )
        )
    if choice.value == "tag":
        return Ok(advance(replace(s, step="tag", idx_summary=choice.index, return_to_summary=True)))
    if choice.value == "notes":
        return Ok(
            advance(replace(s, step="notes", idx_summary=choice.index, return_to_summary=True))
        )
    if choice.value == "start":
        if s.tag is None:
            return Ok(
                advance(replace(s, step="tag", idx_summary=choice.index, return_to_summary=True))
            )
        return Ok(
            advance(replace(s, step="confirm", idx_summary=choice.index, return_to_summary=False))
        )

    return Err(
        ReleaseError(kind="invalid_input", message=f"unknown summary action: {choice.value}")
    )


def _step_notes(
    s: ContentReleaseSession,
) -> Result[StepOutcome[ContentReleaseSession], ReleaseError]:
    next_s = _notes_step(s)
    if isinstance(next_s, Err):
        return next_s
    return Ok(advance(next_s.value))


def _ensure_open_control_clean(
    *,
    workspace_root: Path,
    pinned: tuple[PinnedRepo, ...],
) -> Result[None, ReleaseError]:
    core_pin = next((p for p in pinned if p.repo.id == "core"), None)
    if core_pin is None:
        return Ok(None)

    preflight_oc = preflight_open_control(
        workspace_root=workspace_root,
        core_sha=core_pin.sha,
    )
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


def _validate_content_confirm_inputs(
    session: ContentReleaseSession,
) -> Result[tuple[ReleaseChannel, ReleaseBump, str], ReleaseError]:
    if session.channel is None or session.bump is None or session.tag is None:
        return Err(
            ReleaseError(
                kind="invalid_input",
                message="incomplete content release session; missing channel/bump/tag",
            )
        )
    return Ok((session.channel, session.bump, session.tag))


def _dispatch_content_release(
    *,
    ctx: _ContentCtx,
    session: ContentReleaseSession,
    plan: ReleasePlan,
) -> Result[None, ReleaseError]:
    print_notes_status(
        console=ctx.console,
        notes_markdown=session.notes_markdown,
        notes_path=session.notes_path,
        notes_sha256=session.notes_sha256,
        auto_label="notes: automatic notes only",
    )

    pr = prepare_distribution_pr(
        workspace_root=ctx.workspace_root,
        console=ctx.console,
        plan=plan,
        user_notes=session.notes_markdown,
        user_notes_file=None,
        dry_run=ctx.dry_run,
    )
    if isinstance(pr, Err):
        return pr

    ctx.console.success(f"PR merged: {pr.value}")

    run = publish_distribution_release(
        workspace_root=ctx.workspace_root,
        console=ctx.console,
        plan=plan,
        watch=ctx.watch,
        dry_run=ctx.dry_run,
    )
    if isinstance(run, Err):
        return run

    ctx.console.success(f"Workflow run: {run.value}")
    ctx.console.print(
        "Next: approve the 'release' environment in GitHub Actions to sign + publish.",
        Style.DIM,
    )

    cleared = clear_content_session(workspace_root=ctx.workspace_root)
    if isinstance(cleared, Err):
        return cleared
    return Ok(None)


def _step_confirm(
    s: ContentReleaseSession, *, ctx: _ContentCtx
) -> Result[StepOutcome[ContentReleaseSession], ReleaseError]:
    approved = confirm_yn(prompt=f"Publish content {s.tag or 'unset'}")
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

    clean = _ensure_open_control_clean(workspace_root=ctx.workspace_root, pinned=pinned.value)
    if isinstance(clean, Err):
        return clean

    valid = _validate_content_confirm_inputs(s)
    if isinstance(valid, Err):
        return valid
    channel, bump, tag = valid.value

    planned = plan_release(
        workspace_root=ctx.workspace_root,
        channel=channel,
        bump=bump,
        tag_override=tag,
        pinned=pinned.value,
    )
    if isinstance(planned, Err):
        return planned

    dispatched = _dispatch_content_release(ctx=ctx, session=s, plan=planned.value)
    if isinstance(dispatched, Err):
        return dispatched

    return Ok(FINISH)


def _handlers(*, ctx: _ContentCtx) -> dict[str, StepHandler[ContentReleaseSession]]:
    return {
        "product": _step_product,
        "channel": _step_channel,
        "bump": _step_bump,
        "repo": lambda s: _step_repo(s, ctx=ctx),
        "tag": lambda s: _step_tag(s, ctx=ctx),
        "summary": _step_summary,
        "notes": _step_notes,
        "confirm": lambda s: _step_confirm(s, ctx=ctx),
    }


def run_guided_content_release(
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
        permission_check=ensure_release_permissions,
    )
    if isinstance(preflight, Err):
        return preflight

    boot = bootstrap_content_session(
        workspace_root=workspace_root,
        created_by=preflight.value,
        notes_file=notes_file,
    )
    if isinstance(boot, Err):
        return boot

    saved = save_content_state(workspace_root=workspace_root, session=boot.value)
    if isinstance(saved, Err):
        return saved

    ctx = _ContentCtx(
        workspace_root=workspace_root,
        console=console,
        watch=watch,
        dry_run=dry_run,
    )
    return run_state_machine(
        initial_state=saved.value,
        get_step=lambda s: s.step,
        handlers=_handlers(ctx=ctx),
        save_state=lambda s: save_content_state(workspace_root=workspace_root, session=s),
    )
