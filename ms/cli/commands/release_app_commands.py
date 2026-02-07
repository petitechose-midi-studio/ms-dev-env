from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import typer

from ms.cli.commands.release_common import (
    confirm_tag as confirm_release_tag,
)
from ms.cli.commands.release_common import (
    enforce_auto_constraints,
    ensure_release_permissions_or_exit,
    exit_release,
    parse_overrides,
    pick_pinned_repo_interactive,
    print_current_release_user,
    resolve_release_inputs,
)
from ms.cli.context import CLIContext, build_context
from ms.core.errors import ErrorCode
from ms.core.result import Err
from ms.output.console import ConsoleProtocol, Style
from ms.services.release import config
from ms.services.release.auto import resolve_pinned_auto_strict
from ms.services.release.model import PinnedRepo, ReleaseBump, ReleaseChannel, ReleaseRepo
from ms.services.release.notes import load_external_notes_file
from ms.services.release.plan_file import PlanInput, write_plan_file
from ms.services.release.service import (
    ensure_app_release_permissions,
    ensure_ci_green,
    plan_app_release,
    prepare_app_pr,
    publish_app_release,
)


def _resolve_pinned_app(
    *,
    workspace_root: Path,
    console: ConsoleProtocol,
    repo_overrides: list[str],
    ref_overrides: list[str],
    auto: bool,
    allow_non_green: bool,
    interactive: bool,
) -> tuple[PinnedRepo, ...]:
    overrides = parse_overrides(repo_overrides, flag="--repo")
    refs = parse_overrides(ref_overrides, flag="--ref")

    repo = config.APP_RELEASE_REPO
    ref = refs.get(repo.id, repo.ref)
    repo_sel = ReleaseRepo(
        id=repo.id,
        slug=repo.slug,
        ref=ref,
        required_ci_workflow_file=repo.required_ci_workflow_file,
    )

    if auto:
        enforce_auto_constraints(auto=auto, overrides=overrides, allow_non_green=allow_non_green)

        resolved = resolve_pinned_auto_strict(
            workspace_root=workspace_root,
            repos=(repo_sel,),
            ref_overrides={repo.id: ref},
        )
        if isinstance(resolved, Err):
            # Simplified blocker output for app lane.
            console.header("Auto Release Blocked")
            for r in resolved.error:
                console.print(f"- {r.repo.id} ({r.repo.slug})", Style.DIM)
                if r.error is not None:
                    console.error(r.error)
                elif r.status is not None and not r.status.is_clean:
                    console.error("working tree is dirty")
                elif r.head_green is not True:
                    console.error("remote HEAD is not green")
            exit_release("auto release is blocked", code=ErrorCode.USER_ERROR)
        console.success("auto pins: OK")
        return resolved.value

    if repo.id in overrides:
        return (PinnedRepo(repo=repo_sel, sha=overrides[repo.id]),)

    if not interactive:
        exit_release(
            f"missing --repo {repo.id}=<sha> (or run without --no-interactive)",
            code=ErrorCode.USER_ERROR,
        )

    return (
        pick_pinned_repo_interactive(
            workspace_root=workspace_root,
            console=console,
            repo=repo_sel,
            ref=ref,
            allow_non_green=allow_non_green,
        ),
    )


def _print_app_plan(
    *,
    channel: ReleaseChannel,
    tag: str,
    version: str,
    pinned: tuple[PinnedRepo, ...],
    console: ConsoleProtocol,
) -> None:
    console.header("App Release Plan")
    console.print(f"channel: {channel}")
    console.print(f"tag: {tag}")
    console.print(f"version: {version}")
    console.print("repos:")
    for p in pinned:
        console.print(f"- {p.repo.id}: {p.sha}")


def _print_app_replay(
    *,
    channel: ReleaseChannel,
    tag: str,
    pinned: tuple[PinnedRepo, ...],
    console: ConsoleProtocol,
    plan_file: Path | None,
) -> None:
    repo_args = " ".join([f"--repo {p.repo.id}={p.sha}" for p in pinned])
    console.newline()
    console.print("Replay:", Style.DIM)
    if plan_file is not None:
        console.print(f"ms release app publish --plan {plan_file}", Style.DIM)
    console.print(
        f"ms release app publish --channel {channel} --tag {tag} --no-interactive {repo_args}",
        Style.DIM,
    )


def app_plan_cmd(
    channel: ReleaseChannel = typer.Option(..., "--channel", help="stable or beta"),
    bump: ReleaseBump = typer.Option("patch", "--bump", help="major/minor/patch"),
    tag: str | None = typer.Option(None, "--tag", help="Override tag"),
    auto: bool = typer.Option(False, "--auto", help="Auto-select pins (strict)"),
    repo: list[str] = typer.Option([], "--repo", help="Override repo SHA (id=sha)"),
    ref: list[str] = typer.Option([], "--ref", help="Override repo ref (id=ref)"),
    allow_non_green: bool = typer.Option(False, "--allow-non-green", help="Allow non-green SHAs"),
    no_interactive: bool = typer.Option(
        False, "--no-interactive", help="Require explicit --repo overrides"
    ),
    out: Path | None = typer.Option(None, "--out", help="Write plan JSON to file"),
) -> None:
    """Plan an ms-manager app release (no side effects)."""
    ctx = build_context()

    ensure_release_permissions_or_exit(
        workspace_root=ctx.workspace.root,
        console=ctx.console,
        permission_check=ensure_app_release_permissions,
        require_write=False,
        failure_code=ErrorCode.ENV_ERROR,
    )
    print_current_release_user(workspace_root=ctx.workspace.root, console=ctx.console)

    pinned = _resolve_pinned_app(
        workspace_root=ctx.workspace.root,
        console=ctx.console,
        repo_overrides=repo,
        ref_overrides=ref,
        auto=auto,
        allow_non_green=allow_non_green,
        interactive=not no_interactive,
    )

    planned = plan_app_release(
        workspace_root=ctx.workspace.root,
        channel=channel,
        bump=bump,
        tag_override=tag,
        pinned=pinned,
    )
    if isinstance(planned, Err):
        exit_release(planned.error.message, code=ErrorCode.USER_ERROR)
    app_tag, version = planned.value

    _print_app_plan(
        channel=channel, tag=app_tag, version=version, pinned=pinned, console=ctx.console
    )

    if out is not None:
        plan_file = write_plan_file(
            path=out,
            plan=PlanInput(product="app", channel=channel, tag=app_tag, pinned=pinned),
        )
        if isinstance(plan_file, Err):
            exit_release(plan_file.error.message, code=ErrorCode.IO_ERROR)
        ctx.console.success(str(out))

    _print_app_replay(
        channel=channel, tag=app_tag, pinned=pinned, console=ctx.console, plan_file=out
    )


@dataclass(frozen=True, slots=True)
class _AppReleaseRequest:
    channel: ReleaseChannel
    tag: str
    version: str
    pinned: tuple[PinnedRepo, ...]


@dataclass(frozen=True, slots=True)
class _PreparedAppRelease:
    request: _AppReleaseRequest
    pr_url: str
    source_sha: str


def _prepare_app_release_request(
    *,
    ctx: CLIContext,
    channel: ReleaseChannel | None,
    bump: ReleaseBump,
    tag: str | None,
    auto: bool,
    repo: list[str],
    ref: list[str],
    plan_file: Path | None,
    allow_non_green: bool,
    confirm_tag: str | None,
    no_interactive: bool,
    dry_run: bool,
) -> _AppReleaseRequest:
    resolved = resolve_release_inputs(
        product="app",
        plan=plan_file,
        channel=channel,
        tag=tag,
        auto=auto,
        repo=repo,
        ref=ref,
        resolve_pinned=lambda _selected_channel: _resolve_pinned_app(
            workspace_root=ctx.workspace.root,
            console=ctx.console,
            repo_overrides=repo,
            ref_overrides=ref,
            auto=auto,
            allow_non_green=allow_non_green,
            interactive=not no_interactive,
        ),
    )

    planned = plan_app_release(
        workspace_root=ctx.workspace.root,
        channel=resolved.channel,
        bump=bump,
        tag_override=resolved.tag,
        pinned=resolved.pinned,
    )
    if isinstance(planned, Err):
        exit_release(planned.error.message, code=ErrorCode.USER_ERROR)
    app_tag, version = planned.value

    green = ensure_ci_green(
        workspace_root=ctx.workspace.root,
        pinned=resolved.pinned,
        allow_non_green=allow_non_green,
    )
    if isinstance(green, Err):
        exit_release(green.error.message, code=ErrorCode.USER_ERROR)

    _print_app_plan(
        channel=resolved.channel,
        tag=app_tag,
        version=version,
        pinned=resolved.pinned,
        console=ctx.console,
    )
    _print_app_replay(
        channel=resolved.channel,
        tag=app_tag,
        pinned=resolved.pinned,
        console=ctx.console,
        plan_file=plan_file,
    )
    if not dry_run:
        confirm_release_tag(app_tag, confirm_tag=confirm_tag)

    return _AppReleaseRequest(
        channel=resolved.channel,
        tag=app_tag,
        version=version,
        pinned=resolved.pinned,
    )


def _prepare_app_release(
    *,
    ctx: CLIContext,
    channel: ReleaseChannel | None,
    bump: ReleaseBump,
    tag: str | None,
    auto: bool,
    repo: list[str],
    ref: list[str],
    plan_file: Path | None,
    allow_non_green: bool,
    confirm_tag: str | None,
    no_interactive: bool,
    dry_run: bool,
) -> _PreparedAppRelease:
    request = _prepare_app_release_request(
        ctx=ctx,
        channel=channel,
        bump=bump,
        tag=tag,
        auto=auto,
        repo=repo,
        ref=ref,
        plan_file=plan_file,
        allow_non_green=allow_non_green,
        confirm_tag=confirm_tag,
        no_interactive=no_interactive,
        dry_run=dry_run,
    )

    pr = prepare_app_pr(
        workspace_root=ctx.workspace.root,
        console=ctx.console,
        tag=request.tag,
        version=request.version,
        base_sha=request.pinned[0].sha,
        pinned=request.pinned,
        dry_run=dry_run,
    )
    if isinstance(pr, Err):
        exit_release(pr.error.message, code=ErrorCode.IO_ERROR)

    return _PreparedAppRelease(
        request=request,
        pr_url=pr.value.pr_url,
        source_sha=pr.value.source_sha,
    )


def app_prepare_cmd(
    channel: ReleaseChannel | None = typer.Option(None, "--channel", help="stable or beta"),
    bump: ReleaseBump = typer.Option("patch", "--bump", help="major/minor/patch"),
    tag: str | None = typer.Option(None, "--tag", help="Override tag"),
    auto: bool = typer.Option(False, "--auto", help="Auto-select pins (strict)"),
    repo: list[str] = typer.Option([], "--repo", help="Override repo SHA (id=sha)"),
    ref: list[str] = typer.Option([], "--ref", help="Override repo ref (id=ref)"),
    plan: Path | None = typer.Option(None, "--plan", help="Use a previously saved plan JSON"),
    allow_non_green: bool = typer.Option(False, "--allow-non-green", help="Allow non-green SHAs"),
    confirm_tag: str | None = typer.Option(
        None, "--confirm-tag", help="Skip confirmation prompt by providing the tag"
    ),
    no_interactive: bool = typer.Option(
        False, "--no-interactive", help="Require explicit --repo overrides"
    ),
    dry_run: bool = typer.Option(False, "--dry-run", help="Print actions without mutating"),
) -> None:
    """Create + merge the ms-manager PR for a version bump."""
    ctx = build_context()

    ensure_release_permissions_or_exit(
        workspace_root=ctx.workspace.root,
        console=ctx.console,
        permission_check=ensure_app_release_permissions,
        require_write=True,
        failure_code=ErrorCode.USER_ERROR,
    )

    prepared = _prepare_app_release(
        ctx=ctx,
        channel=channel,
        bump=bump,
        tag=tag,
        auto=auto,
        repo=repo,
        ref=ref,
        plan_file=plan,
        allow_non_green=allow_non_green,
        confirm_tag=confirm_tag,
        no_interactive=no_interactive,
        dry_run=dry_run,
    )

    ctx.console.success(f"PR: {prepared.pr_url}")
    ctx.console.print(f"source sha: {prepared.source_sha}", Style.DIM)


def app_publish_cmd(
    channel: ReleaseChannel | None = typer.Option(None, "--channel", help="stable or beta"),
    bump: ReleaseBump = typer.Option("patch", "--bump", help="major/minor/patch"),
    tag: str | None = typer.Option(None, "--tag", help="Override tag"),
    auto: bool = typer.Option(False, "--auto", help="Auto-select pins (strict)"),
    repo: list[str] = typer.Option([], "--repo", help="Override repo SHA (id=sha)"),
    ref: list[str] = typer.Option([], "--ref", help="Override repo ref (id=ref)"),
    plan: Path | None = typer.Option(None, "--plan", help="Use a previously saved plan JSON"),
    allow_non_green: bool = typer.Option(False, "--allow-non-green", help="Allow non-green SHAs"),
    confirm_tag: str | None = typer.Option(
        None, "--confirm-tag", help="Skip confirmation prompt by providing the tag"
    ),
    no_interactive: bool = typer.Option(
        False, "--no-interactive", help="Require explicit --repo overrides"
    ),
    watch: bool = typer.Option(False, "--watch", help="Watch workflow run until completion"),
    notes_file: Path | None = typer.Option(
        None, "--notes-file", help="Optional markdown notes file"
    ),
    dry_run: bool = typer.Option(False, "--dry-run", help="Print actions without mutating"),
) -> None:
    """Prepare app version PR + dispatch ms-manager Candidate then Release workflows."""
    ctx = build_context()

    ensure_release_permissions_or_exit(
        workspace_root=ctx.workspace.root,
        console=ctx.console,
        permission_check=ensure_app_release_permissions,
        require_write=True,
        failure_code=ErrorCode.USER_ERROR,
    )

    prepared = _prepare_app_release(
        ctx=ctx,
        channel=channel,
        bump=bump,
        tag=tag,
        auto=auto,
        repo=repo,
        ref=ref,
        plan_file=plan,
        allow_non_green=allow_non_green,
        confirm_tag=confirm_tag,
        no_interactive=no_interactive,
        dry_run=dry_run,
    )

    notes_markdown: str | None = None
    notes_source_path: str | None = None
    if notes_file is not None:
        notes_r = load_external_notes_file(path=notes_file)
        if isinstance(notes_r, Err):
            exit_release(notes_r.error.message, code=ErrorCode.USER_ERROR)
        notes_markdown = notes_r.value.markdown
        notes_source_path = str(notes_r.value.source_path.resolve())
        ctx.console.print(
            f"notes: attached from {notes_source_path} (sha256={notes_r.value.sha256[:12]})",
            Style.DIM,
        )

    ctx.console.success(f"PR merged: {prepared.pr_url}")
    ctx.console.print(f"source sha: {prepared.source_sha}", Style.DIM)

    run = publish_app_release(
        workspace_root=ctx.workspace.root,
        console=ctx.console,
        tag=prepared.request.tag,
        source_sha=prepared.source_sha,
        notes_markdown=notes_markdown,
        notes_source_path=notes_source_path,
        watch=watch,
        dry_run=dry_run,
    )
    if isinstance(run, Err):
        exit_release(run.error.message, code=ErrorCode.NETWORK_ERROR)

    candidate_url, release_url = run.value
    ctx.console.success(f"Candidate run: {candidate_url}")
    ctx.console.success(f"Release run: {release_url}")
    ctx.console.print(
        "Next: approve the 'app-release' environment in GitHub Actions to publish.",
        Style.DIM,
    )


def register_app_commands(*, namespace: typer.Typer) -> None:
    namespace.command("plan")(app_plan_cmd)
    namespace.command("prepare")(app_prepare_cmd)
    namespace.command("publish")(app_publish_cmd)
