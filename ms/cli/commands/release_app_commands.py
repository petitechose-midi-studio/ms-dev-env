from __future__ import annotations

from pathlib import Path

import typer

from ms.cli.commands.release_common import (
    confirm_tag as confirm_release_tag,
)
from ms.cli.commands.release_common import (
    ensure_release_permissions_or_exit,
    exit_release,
    pick_pinned_repo_interactive,
    print_current_release_user,
    resolve_release_inputs,
)
from ms.cli.context import CLIContext, build_context
from ms.core.errors import ErrorCode
from ms.core.result import Err
from ms.output.console import ConsoleProtocol, Style
from ms.release.domain import AppReleasePlan, PinnedRepo, ReleaseBump, ReleaseChannel, config
from ms.release.flow.app_plan import build_app_release_plan, plan_app_release
from ms.release.flow.app_prepare import (
    PreparedAppRelease,
    prepare_app_pr,
    prepare_app_release_distribution,
)
from ms.release.flow.app_publish import (
    publish_app_release,
    publish_app_release_workflows,
    resolve_app_publish_notes,
)
from ms.release.flow.ci_gate import ensure_ci_green
from ms.release.flow.permissions import ensure_app_release_permissions
from ms.release.infra.artifacts.notes_writer import load_external_notes_file
from ms.release.resolve.app_inputs import resolve_pinned_app
from ms.release.resolve.auto.strict import resolve_pinned_auto_strict
from ms.release.resolve.plan_io import PlanInput, write_plan_file
from ms.release.view.app_console import (
    print_app_auto_blockers,
    print_app_notes_attachment,
    print_app_plan,
    print_app_replay,
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
    resolved = resolve_pinned_app(
        workspace_root=workspace_root,
        app_release_repo=config.APP_RELEASE_REPO,
        repo_overrides=repo_overrides,
        ref_overrides=ref_overrides,
        auto=auto,
        allow_non_green=allow_non_green,
        interactive=interactive,
        auto_resolver=lambda current_workspace, repos, current_refs: resolve_pinned_auto_strict(
            workspace_root=current_workspace,
            repos=repos,
            ref_overrides=current_refs,
        ),
        picker=lambda repo, ref: pick_pinned_repo_interactive(
            workspace_root=workspace_root,
            console=console,
            repo=repo,
            ref=ref,
            allow_non_green=allow_non_green,
        ),
    )
    if isinstance(resolved, Err):
        exit_release(resolved.error.message, code=ErrorCode.USER_ERROR)

    if resolved.value.blockers:
        print_app_auto_blockers(console=console, blockers=resolved.value.blockers)
        exit_release("auto release is blocked", code=ErrorCode.USER_ERROR)

    if auto:
        console.success("auto pins: OK")

    if resolved.value.pinned is None:
        exit_release("auto release is blocked", code=ErrorCode.USER_ERROR)
    return resolved.value.pinned


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

    planned = build_app_release_plan(
        planner=plan_app_release,
        workspace_root=ctx.workspace.root,
        channel=channel,
        bump=bump,
        tag_override=tag,
        pinned=pinned,
    )
    if isinstance(planned, Err):
        exit_release(planned.error.message, code=ErrorCode.USER_ERROR)

    print_app_plan(plan=planned.value, console=ctx.console)

    if out is not None:
        plan_file = write_plan_file(
            path=out,
            plan=PlanInput(
                product="app",
                channel=planned.value.channel,
                tag=planned.value.tag,
                pinned=planned.value.pinned,
            ),
        )
        if isinstance(plan_file, Err):
            exit_release(plan_file.error.message, code=ErrorCode.IO_ERROR)
        ctx.console.success(str(out))

    print_app_replay(plan=planned.value, console=ctx.console, plan_file=out)


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
) -> AppReleasePlan:
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

    planned = build_app_release_plan(
        planner=plan_app_release,
        workspace_root=ctx.workspace.root,
        channel=resolved.channel,
        bump=bump,
        tag_override=resolved.tag,
        pinned=resolved.pinned,
    )
    if isinstance(planned, Err):
        exit_release(planned.error.message, code=ErrorCode.USER_ERROR)

    print_app_plan(plan=planned.value, console=ctx.console)
    print_app_replay(plan=planned.value, console=ctx.console, plan_file=plan_file)
    if not dry_run:
        confirm_release_tag(planned.value.tag, confirm_tag=confirm_tag)

    return planned.value


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
) -> PreparedAppRelease:
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

    prepared = prepare_app_release_distribution(
        ensure_ci_green_fn=ensure_ci_green,
        prepare_app_pr_fn=prepare_app_pr,
        workspace_root=ctx.workspace.root,
        console=ctx.console,
        plan=request,
        allow_non_green=allow_non_green,
        dry_run=dry_run,
    )
    if isinstance(prepared, Err):
        code = (
            ErrorCode.IO_ERROR
            if prepared.error.kind in {"repo_failed", "repo_dirty"}
            else ErrorCode.USER_ERROR
        )
        exit_release(prepared.error.message, code=code)

    return prepared.value


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

    ctx.console.success(f"PR: {prepared.pr}")
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

    notes = resolve_app_publish_notes(
        notes_file=notes_file,
        load_external_notes_file_fn=load_external_notes_file,
    )
    if isinstance(notes, Err):
        exit_release(notes.error.message, code=ErrorCode.USER_ERROR)

    print_app_notes_attachment(console=ctx.console, notes=notes.value)

    ctx.console.success(f"PR merged: {prepared.pr}")
    ctx.console.print(f"source sha: {prepared.source_sha}", Style.DIM)

    run = publish_app_release_workflows(
        publish_app_release_fn=publish_app_release,
        workspace_root=ctx.workspace.root,
        console=ctx.console,
        prepared=prepared,
        notes=notes.value,
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
