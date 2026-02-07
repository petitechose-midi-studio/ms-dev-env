from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
from typing import Literal, Protocol

from ms.cli.selector import SelectorResult
from ms.core.result import Err, Ok, Result
from ms.output.console import ConsoleProtocol, Style
from ms.release.domain.models import PinnedRepo, ReleaseRepo
from ms.release.errors import ReleaseError

from .fsm import FINISH, StepHandler, StepOutcome, advance, run_state_machine
from .sessions import AppReleaseSession


@dataclass(frozen=True, slots=True)
class MenuOption[T]:
    value: T
    label: str
    detail: str | None = None


class AppPrepareResultLike(Protocol):
    @property
    def pr_url(self) -> str: ...

    @property
    def source_sha(self) -> str: ...


class AppGuidedDependencies[PrepareT: AppPrepareResultLike](Protocol):
    def preflight(self) -> Result[str, ReleaseError]: ...

    def bootstrap_session(
        self, *, created_by: str, notes_file: Path | None
    ) -> Result[AppReleaseSession, ReleaseError]: ...

    def save_state(
        self, *, session: AppReleaseSession
    ) -> Result[AppReleaseSession, ReleaseError]: ...

    def clear_session(self) -> Result[None, ReleaseError]: ...

    def select_channel(
        self, *, title: str, subtitle: str, initial_index: int, allow_back: bool
    ) -> SelectorResult[Literal["stable", "beta"]]: ...

    def select_bump(
        self, *, title: str, subtitle: str, initial_index: int, allow_back: bool
    ) -> SelectorResult[Literal["major", "minor", "patch"]]: ...

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
    ) -> Result[SelectorResult[str], ReleaseError]: ...

    def select_menu(
        self,
        *,
        title: str,
        subtitle: str,
        options: list[MenuOption[str]],
        initial_index: int,
        allow_back: bool,
    ) -> SelectorResult[str]: ...

    def confirm(self, *, prompt: str) -> bool: ...

    def ensure_ci_green(
        self,
        *,
        workspace_root: Path,
        pinned: tuple[PinnedRepo, ...],
        allow_non_green: bool,
    ) -> Result[None, ReleaseError]: ...

    def plan_app_release(
        self,
        *,
        workspace_root: Path,
        channel: Literal["stable", "beta"],
        bump: Literal["major", "minor", "patch"],
        tag_override: str | None,
        pinned: tuple[PinnedRepo, ...],
    ) -> Result[tuple[str, str], ReleaseError]: ...

    def prepare_app_pr(
        self,
        *,
        workspace_root: Path,
        console: ConsoleProtocol,
        tag: str,
        version: str,
        base_sha: str,
        pinned: tuple[PinnedRepo, ...],
        dry_run: bool,
    ) -> Result[PrepareT, ReleaseError]: ...

    def publish_app_release(
        self,
        *,
        workspace_root: Path,
        console: ConsoleProtocol,
        tag: str,
        source_sha: str,
        notes_markdown: str | None,
        notes_source_path: str | None,
        watch: bool,
        dry_run: bool,
    ) -> Result[tuple[str, str], ReleaseError]: ...

    def print_notes_status(
        self,
        *,
        console: ConsoleProtocol,
        notes_markdown: str | None,
        notes_path: str | None,
        notes_sha256: str | None,
        auto_label: str,
    ) -> None: ...


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
    @dataclass(frozen=True, slots=True)
    class _AppCtx:
        workspace_root: Path
        console: ConsoleProtocol
        watch: bool
        dry_run: bool

    def _app_repo(ref: str) -> ReleaseRepo:
        return ReleaseRepo(
            id=app_release_repo.id,
            slug=app_release_repo.slug,
            ref=ref,
            required_ci_workflow_file=app_release_repo.required_ci_workflow_file,
        )

    def _pinned(session: AppReleaseSession) -> Result[tuple[PinnedRepo, ...], ReleaseError]:
        if session.repo_sha is None:
            return Err(
                ReleaseError(kind="invalid_input", message="missing selected app source sha")
            )
        return Ok((PinnedRepo(repo=_app_repo(session.repo_ref), sha=session.repo_sha),))

    def _notes_step(session: AppReleaseSession) -> Result[AppReleaseSession, ReleaseError]:
        choice = deps.select_menu(
            title="Release Notes",
            subtitle="External notes are optional and prepended above auto-notes",
            options=[
                MenuOption(
                    value="keep",
                    label=(
                        "Keep notes"
                        if session.notes_markdown is not None
                        else "No notes configured"
                    ),
                    detail=(
                        session.notes_path
                        if session.notes_path is not None
                        else "Provide --notes-file to set notes"
                    ),
                ),
                *(
                    [
                        MenuOption(
                            value="clear",
                            label="Remove notes",
                            detail="Publish release with automatic notes only",
                        )
                    ]
                    if session.notes_markdown is not None
                    else []
                ),
            ],
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

    def _step_sha(
        s: AppReleaseSession, *, ctx: _AppCtx
    ) -> Result[StepOutcome[AppReleaseSession], ReleaseError]:
        commit = deps.select_green_commit(
            workspace_root=ctx.workspace_root,
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

    def _step_tag(
        s: AppReleaseSession, *, ctx: _AppCtx
    ) -> Result[StepOutcome[AppReleaseSession], ReleaseError]:
        if s.channel is None or s.bump is None:
            return Err(ReleaseError(kind="invalid_input", message="missing channel/bump selection"))
        pinned = _pinned(s)
        if isinstance(pinned, Err):
            return pinned

        planned = deps.plan_app_release(
            workspace_root=ctx.workspace_root,
            channel=s.channel,
            bump=s.bump,
            tag_override=None,
            pinned=pinned.value,
        )
        if isinstance(planned, Err):
            return planned
        tag, version = planned.value

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
            advance(replace(s, tag=tag, version=version, step="summary", return_to_summary=False))
        )

    def _step_summary(s: AppReleaseSession) -> Result[StepOutcome[AppReleaseSession], ReleaseError]:
        notes_label = s.notes_path or "none"
        options = [
            MenuOption(value="channel", label=f"Channel: {s.channel}", detail="Edit channel"),
            MenuOption(value="bump", label=f"Bump: {s.bump}", detail="Edit semantic bump"),
            MenuOption(
                value="sha",
                label=f"Source SHA: {(s.repo_sha or 'unset')[:12]}",
                detail="Edit selected source commit",
            ),
            MenuOption(value="tag", label=f"Tag: {s.tag}", detail=f"Version: {s.version}"),
            MenuOption(
                value="notes",
                label=f"Notes file: {notes_label}",
                detail="Optional attached notes",
            ),
            MenuOption(
                value="start",
                label="Start release",
                detail="Continue to final confirmation",
            ),
        ]
        choice = deps.select_menu(
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
        prepared = deps.prepare_app_pr(
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
        deps.print_notes_status(
            console=ctx.console,
            notes_markdown=session.notes_markdown,
            notes_path=session.notes_path,
            notes_sha256=session.notes_sha256,
            auto_label="notes: automatic notes only",
        )

        run = deps.publish_app_release(
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

        cleared = deps.clear_session()
        if isinstance(cleared, Err):
            return cleared
        return Ok(None)

    def _step_confirm(
        s: AppReleaseSession, *, ctx: _AppCtx
    ) -> Result[StepOutcome[AppReleaseSession], ReleaseError]:
        approved = deps.confirm(
            prompt=f"Publish {s.tag} from {s.repo_sha[:12] if s.repo_sha else 'unset'}"
        )
        if not approved:
            return Ok(advance(replace(s, step="summary")))

        pinned = _pinned(s)
        if isinstance(pinned, Err):
            return pinned

        green = deps.ensure_ci_green(
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

    preflight = deps.preflight()
    if isinstance(preflight, Err):
        return preflight

    boot = deps.bootstrap_session(created_by=preflight.value, notes_file=notes_file)
    if isinstance(boot, Err):
        return boot

    saved = deps.save_state(session=boot.value)
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
        save_state=lambda s: deps.save_state(session=s),
    )
