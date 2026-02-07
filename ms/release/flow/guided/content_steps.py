from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
from typing import Literal, Protocol

from ms.core.result import Err, Ok, Result
from ms.output.console import ConsoleProtocol, Style
from ms.release.domain.models import PinnedRepo, ReleasePlan, ReleaseRepo
from ms.release.errors import ReleaseError

from .fsm import FINISH, StepHandler, StepOutcome, advance, run_state_machine
from .selection import Selection
from .sessions import ContentReleaseSession


@dataclass(frozen=True, slots=True)
class MenuOption[T]:
    value: T
    label: str
    detail: str | None = None


class OpenControlPreflightLike(Protocol):
    def dirty_repos(self) -> object: ...


class ContentGuidedDependencies(Protocol):
    def preflight(self) -> Result[str, ReleaseError]: ...

    def bootstrap_session(
        self, *, created_by: str, notes_file: Path | None
    ) -> Result[ContentReleaseSession, ReleaseError]: ...

    def save_state(
        self, *, session: ContentReleaseSession
    ) -> Result[ContentReleaseSession, ReleaseError]: ...

    def clear_session(self) -> Result[None, ReleaseError]: ...

    def select_channel(
        self, *, title: str, subtitle: str, initial_index: int, allow_back: bool
    ) -> Selection[Literal["stable", "beta"]]: ...

    def select_bump(
        self, *, title: str, subtitle: str, initial_index: int, allow_back: bool
    ) -> Selection[Literal["major", "minor", "patch"]]: ...

    def select_green_commit(
        self,
        *,
        workspace_root: Path,
        repo_slug: str,
        ref: str,
        workflow_file: str | None,
        title: str,
        subtitle: str,
        current_sha: str | None,
        initial_index: int,
        allow_back: bool,
    ) -> Result[Selection[str], ReleaseError]: ...

    def select_menu(
        self,
        *,
        title: str,
        subtitle: str,
        options: list[MenuOption[str]],
        initial_index: int,
        allow_back: bool,
    ) -> Selection[str]: ...

    def confirm(self, *, prompt: str) -> bool: ...

    def ensure_ci_green(
        self,
        *,
        workspace_root: Path,
        pinned: tuple[PinnedRepo, ...],
        allow_non_green: bool,
    ) -> Result[None, ReleaseError]: ...

    def preflight_open_control(
        self,
        *,
        workspace_root: Path,
        core_sha: str,
    ) -> OpenControlPreflightLike: ...

    def plan_release(
        self,
        *,
        workspace_root: Path,
        channel: Literal["stable", "beta"],
        bump: Literal["major", "minor", "patch"],
        tag_override: str | None,
        pinned: tuple[PinnedRepo, ...],
    ) -> Result[ReleasePlan, ReleaseError]: ...

    def prepare_distribution_pr(
        self,
        *,
        workspace_root: Path,
        console: ConsoleProtocol,
        plan: ReleasePlan,
        user_notes: str | None,
        user_notes_file: Path | None,
        dry_run: bool,
    ) -> Result[str, ReleaseError]: ...

    def publish_distribution_release(
        self,
        *,
        workspace_root: Path,
        console: ConsoleProtocol,
        plan: ReleasePlan,
        watch: bool,
        dry_run: bool,
    ) -> Result[str, ReleaseError]: ...

    def print_notes_status(
        self,
        *,
        console: ConsoleProtocol,
        notes_markdown: str | None,
        notes_path: str | None,
        notes_sha256: str | None,
        auto_label: str,
    ) -> None: ...


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
    @dataclass(frozen=True, slots=True)
    class _ContentCtx:
        workspace_root: Path
        console: ConsoleProtocol
        watch: bool
        dry_run: bool

    def _sha_map(session: ContentReleaseSession) -> dict[str, str]:
        return {repo_id: sha for repo_id, sha in session.repo_shas}

    def _set_sha(
        session: ContentReleaseSession, *, repo_id: str, sha: str
    ) -> ContentReleaseSession:
        by_id = _sha_map(session)
        by_id[repo_id] = sha
        ordered = tuple((repo.id, by_id[repo.id]) for repo in release_repos if repo.id in by_id)
        return replace(session, repo_shas=ordered)

    def _pinned(session: ContentReleaseSession) -> Result[tuple[PinnedRepo, ...], ReleaseError]:
        by_id = _sha_map(session)
        missing = [repo.id for repo in release_repos if repo.id not in by_id]
        if missing:
            return Err(
                ReleaseError(
                    kind="invalid_input",
                    message=f"missing selected source sha for: {', '.join(missing)}",
                )
            )
        return Ok(tuple(PinnedRepo(repo=repo, sha=by_id[repo.id]) for repo in release_repos))

    def _notes_step(session: ContentReleaseSession) -> Result[ContentReleaseSession, ReleaseError]:
        options: list[MenuOption[str]] = [
            MenuOption(
                value="keep",
                label=(
                    "Keep notes" if session.notes_markdown is not None else "No notes configured"
                ),
                detail=(
                    session.notes_path
                    if session.notes_path is not None
                    else "Provide --notes-file to set notes"
                ),
            )
        ]
        if session.notes_markdown is not None:
            options.append(
                MenuOption(
                    value="clear",
                    label="Remove notes",
                    detail="Publish content release with generated notes only",
                )
            )

        choice = deps.select_menu(
            title="Content Notes",
            subtitle="External notes are optional",
            options=options,
            initial_index=0,
            allow_back=True,
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
        *,
        ctx: _ContentCtx,
    ) -> Result[StepOutcome[ContentReleaseSession], ReleaseError]:
        current = session
        if current.repo_cursor < 0 or current.repo_cursor >= len(release_repos):
            current = replace(current, repo_cursor=0)

        repo = release_repos[current.repo_cursor]
        current_sha = _sha_map(current).get(repo.id)
        commit = deps.select_green_commit(
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

        if choice.value is None:
            return Err(ReleaseError(kind="invalid_input", message="missing repo sha selection"))
        next_session = _set_sha(current, repo_id=repo.id, sha=choice.value)
        next_session = replace(next_session, idx_repo=choice.index)
        if next_session.return_to_summary:
            return Ok(advance(replace(next_session, step="summary", return_to_summary=False)))
        if next_session.repo_cursor + 1 < len(release_repos):
            return Ok(advance(replace(next_session, repo_cursor=next_session.repo_cursor + 1)))
        return Ok(advance(replace(next_session, step="tag")))

    def _step_tag(
        session: ContentReleaseSession,
        *,
        ctx: _ContentCtx,
    ) -> Result[StepOutcome[ContentReleaseSession], ReleaseError]:
        if session.channel is None or session.bump is None:
            return Err(ReleaseError(kind="invalid_input", message="missing channel/bump selection"))
        pinned = _pinned(session)
        if isinstance(pinned, Err):
            return pinned

        planned = deps.plan_release(
            workspace_root=ctx.workspace_root,
            channel=session.channel,
            bump=session.bump,
            tag_override=None,
            pinned=pinned.value,
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
        sha_by_id = _sha_map(session)
        notes_label = session.notes_path or "none"
        options: list[MenuOption[str]] = [
            MenuOption(value="channel", label=f"Channel: {session.channel}", detail="Edit channel"),
            MenuOption(value="bump", label=f"Bump: {session.bump}", detail="Edit semantic bump"),
        ]
        for idx, repo in enumerate(release_repos):
            options.append(
                MenuOption(
                    value=f"repo:{idx}",
                    label=f"{repo.id}: {(sha_by_id.get(repo.id, 'unset'))[:12]}",
                    detail=repo.slug,
                )
            )
        options.extend(
            [
                MenuOption(value="tag", label=f"Tag: {session.tag}", detail="Computed release tag"),
                MenuOption(
                    value="notes",
                    label=f"Notes file: {notes_label}",
                    detail="Optional release notes",
                ),
                MenuOption(
                    value="start",
                    label="Start release",
                    detail="Continue to final confirmation",
                ),
            ]
        )

        choice = deps.select_menu(
            title="Content Release Summary",
            subtitle="Select an item to edit, or start release",
            options=options,
            initial_index=session.idx_summary,
            allow_back=True,
        )
        if choice.action == "cancel":
            return Err(ReleaseError(kind="invalid_input", message="release cancelled"))
        if choice.action == "back":
            return Ok(advance(replace(session, step="tag")))
        if choice.value is None:
            return Err(ReleaseError(kind="invalid_input", message="missing summary action"))

        if choice.value == "channel":
            return Ok(
                advance(
                    replace(
                        session,
                        step="channel",
                        idx_summary=choice.index,
                        return_to_summary=True,
                    )
                )
            )
        if choice.value == "bump":
            return Ok(
                advance(
                    replace(
                        session,
                        step="bump",
                        idx_summary=choice.index,
                        return_to_summary=True,
                    )
                )
            )
        if choice.value.startswith("repo:"):
            idx = int(choice.value.split(":", 1)[1])
            return Ok(
                advance(
                    replace(
                        session,
                        step="repo",
                        repo_cursor=max(0, min(idx, len(release_repos) - 1)),
                        idx_summary=choice.index,
                        return_to_summary=True,
                    )
                )
            )
        if choice.value == "tag":
            return Ok(
                advance(
                    replace(
                        session,
                        step="tag",
                        idx_summary=choice.index,
                        return_to_summary=True,
                    )
                )
            )
        if choice.value == "notes":
            return Ok(
                advance(
                    replace(
                        session,
                        step="notes",
                        idx_summary=choice.index,
                        return_to_summary=True,
                    )
                )
            )
        if choice.value == "start":
            if session.tag is None:
                return Ok(
                    advance(
                        replace(
                            session,
                            step="tag",
                            idx_summary=choice.index,
                            return_to_summary=True,
                        )
                    )
                )
            return Ok(
                advance(
                    replace(
                        session,
                        step="confirm",
                        idx_summary=choice.index,
                        return_to_summary=False,
                    )
                )
            )

        return Err(
            ReleaseError(kind="invalid_input", message=f"unknown summary action: {choice.value}")
        )

    def _step_notes(
        session: ContentReleaseSession,
    ) -> Result[StepOutcome[ContentReleaseSession], ReleaseError]:
        next_session = _notes_step(session)
        if isinstance(next_session, Err):
            return next_session
        return Ok(advance(next_session.value))

    def _ensure_open_control_clean(
        *,
        workspace_root: Path,
        pinned: tuple[PinnedRepo, ...],
    ) -> Result[None, ReleaseError]:
        core_pin = next((pin for pin in pinned if pin.repo.id == "core"), None)
        if core_pin is None:
            return Ok(None)

        preflight_oc = deps.preflight_open_control(
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

    def _dispatch_content_release(
        *,
        ctx: _ContentCtx,
        session: ContentReleaseSession,
        plan: ReleasePlan,
    ) -> Result[None, ReleaseError]:
        deps.print_notes_status(
            console=ctx.console,
            notes_markdown=session.notes_markdown,
            notes_path=session.notes_path,
            notes_sha256=session.notes_sha256,
            auto_label="notes: automatic notes only",
        )

        pr = deps.prepare_distribution_pr(
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

        run = deps.publish_distribution_release(
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

        cleared = deps.clear_session()
        if isinstance(cleared, Err):
            return cleared
        return Ok(None)

    def _step_confirm(
        session: ContentReleaseSession,
        *,
        ctx: _ContentCtx,
    ) -> Result[StepOutcome[ContentReleaseSession], ReleaseError]:
        approved = deps.confirm(prompt=f"Publish content {session.tag or 'unset'}")
        if not approved:
            return Ok(advance(replace(session, step="summary")))

        pinned = _pinned(session)
        if isinstance(pinned, Err):
            return pinned

        green = deps.ensure_ci_green(
            workspace_root=ctx.workspace_root,
            pinned=pinned.value,
            allow_non_green=False,
        )
        if isinstance(green, Err):
            return green

        clean = _ensure_open_control_clean(workspace_root=ctx.workspace_root, pinned=pinned.value)
        if isinstance(clean, Err):
            return clean

        valid = _validate_content_confirm_inputs(session)
        if isinstance(valid, Err):
            return valid
        channel, bump, tag = valid.value

        planned = deps.plan_release(
            workspace_root=ctx.workspace_root,
            channel=channel,
            bump=bump,
            tag_override=tag,
            pinned=pinned.value,
        )
        if isinstance(planned, Err):
            return planned

        dispatched = _dispatch_content_release(ctx=ctx, session=session, plan=planned.value)
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

    preflight = deps.preflight()
    if isinstance(preflight, Err):
        return preflight

    boot = deps.bootstrap_session(created_by=preflight.value, notes_file=notes_file)
    if isinstance(boot, Err):
        return boot

    saved = deps.save_state(session=boot.value)
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
        save_state=lambda s: deps.save_state(session=s),
    )
