from __future__ import annotations

from pathlib import Path

import typer

from ms.cli.commands.release_common import (
    confirm_tag as confirm_release_tag,
)
from ms.cli.commands.release_common import (
    ensure_release_permissions_or_exit,
    exit_release,
    resolve_release_inputs,
)
from ms.cli.context import CLIContext, build_context
from ms.core.errors import ErrorCode
from ms.core.result import Err
from ms.output.console import Style
from ms.release.domain import AppReleasePlan, ReleaseBump, ReleaseChannel
from ms.release.flow.app_plan import plan_app_release
from ms.release.flow.app_prepare import (
    PreparedAppRelease,
    prepare_app_release_distribution,
)
from ms.release.flow.permissions import ensure_app_release_permissions
from ms.release.view.app_console import print_app_plan, print_app_replay

from .release_app_common import resolve_app_pinned_or_exit


def prepare_app_release_request(
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
        resolve_pinned=lambda _selected_channel: resolve_app_pinned_or_exit(
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

    print_app_plan(plan=planned.value, console=ctx.console)
    print_app_replay(plan=planned.value, console=ctx.console, plan_file=plan_file)
    if not dry_run:
        confirm_release_tag(planned.value.tag, confirm_tag=confirm_tag)

    return planned.value


def prepare_app_release(
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
    request = prepare_app_release_request(
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

    prepared = prepare_app_release(
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
