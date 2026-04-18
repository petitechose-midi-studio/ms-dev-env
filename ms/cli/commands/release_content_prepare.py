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
from ms.release.domain import ReleaseBump, ReleaseChannel
from ms.release.flow.content_plan import plan_release
from ms.release.flow.content_preflight import load_open_control_report
from ms.release.flow.content_prepare import (
    PreparedContentRelease,
    prepare_content_release_distribution,
)
from ms.release.flow.permissions import ensure_release_permissions
from ms.release.view.content_console import (
    print_content_plan,
    print_content_replay,
    print_open_control_preflight,
)

from .release_content_common import resolve_pinned_or_exit


def prepare_content_release(
    *,
    ctx: CLIContext,
    channel: ReleaseChannel | None,
    bump: ReleaseBump,
    tag: str | None,
    auto: bool,
    repo: list[str],
    ref: list[str],
    plan_file: Path | None,
    notes: str | None,
    notes_file: Path | None,
    allow_non_green: bool,
    allow_open_control_dirty: bool,
    confirm_tag: str | None,
    no_interactive: bool,
    dry_run: bool,
) -> PreparedContentRelease:
    resolved = resolve_release_inputs(
        product="content",
        plan=plan_file,
        channel=channel,
        tag=tag,
        auto=auto,
        repo=repo,
        ref=ref,
        resolve_pinned=lambda selected_channel: resolve_pinned_or_exit(
            workspace_root=ctx.workspace.root,
            console=ctx.console,
            channel=selected_channel,
            repo_overrides=repo,
            ref_overrides=ref,
            auto=auto,
            allow_non_green=allow_non_green,
            interactive=not no_interactive,
        ),
    )

    report = load_open_control_report(
        workspace_root=ctx.workspace.root,
        pinned=resolved.pinned,
    )
    if report is not None:
        print_open_control_preflight(console=ctx.console, report=report)
    if report is not None and report.dirty_repos() and not allow_open_control_dirty:
        exit_release(
            "open-control has uncommitted changes (release builds may differ from dev symlink)",
            code=ErrorCode.USER_ERROR,
        )

    planned = plan_release(
        workspace_root=ctx.workspace.root,
        channel=resolved.channel,
        bump=bump,
        tag_override=resolved.tag,
        pinned=resolved.pinned,
        tooling_override=resolved.tooling,
    )
    if isinstance(planned, Err):
        exit_release(planned.error.message, code=ErrorCode.USER_ERROR)

    print_content_plan(plan=planned.value, console=ctx.console)
    print_content_replay(plan=planned.value, console=ctx.console, plan_file=plan_file)
    if not dry_run:
        confirm_release_tag(planned.value.tag, confirm_tag=confirm_tag)

    prepared = prepare_content_release_distribution(
        workspace_root=ctx.workspace.root,
        console=ctx.console,
        plan=planned.value,
        pinned=resolved.pinned,
        notes=notes,
        notes_file=notes_file,
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


def prepare_cmd(
    channel: ReleaseChannel | None = typer.Option(None, "--channel", help="stable or beta"),
    bump: ReleaseBump = typer.Option("patch", "--bump", help="major/minor/patch"),
    tag: str | None = typer.Option(None, "--tag", help="Override tag"),
    auto: bool = typer.Option(False, "--auto", help="Auto-select pins (strict)"),
    repo: list[str] = typer.Option([], "--repo", help="Override repo SHA (id=sha)"),
    ref: list[str] = typer.Option([], "--ref", help="Override repo ref (id=ref)"),
    plan: Path | None = typer.Option(None, "--plan", help="Use a previously saved plan JSON"),
    notes: str | None = typer.Option(None, "--notes", help="Short release notes"),
    notes_file: Path | None = typer.Option(None, "--notes-file", help="Extra markdown file"),
    allow_non_green: bool = typer.Option(False, "--allow-non-green", help="Allow non-green SHAs"),
    allow_open_control_dirty: bool = typer.Option(
        False,
        "--allow-open-control-dirty",
        help="Allow dirty open-control repos (dev symlink drift)",
    ),
    confirm_tag: str | None = typer.Option(
        None, "--confirm-tag", help="Skip confirmation prompt by providing the tag"
    ),
    no_interactive: bool = typer.Option(
        False, "--no-interactive", help="Require explicit --repo overrides"
    ),
    dry_run: bool = typer.Option(False, "--dry-run", help="Print actions without mutating"),
) -> None:
    """Create + merge the distribution PR for a release spec."""
    ctx = build_context()

    ensure_release_permissions_or_exit(
        workspace_root=ctx.workspace.root,
        console=ctx.console,
        permission_check=ensure_release_permissions,
        require_write=True,
        failure_code=ErrorCode.USER_ERROR,
    )

    prepared = prepare_content_release(
        ctx=ctx,
        channel=channel,
        bump=bump,
        tag=tag,
        auto=auto,
        repo=repo,
        ref=ref,
        plan_file=plan,
        notes=notes,
        notes_file=notes_file,
        allow_non_green=allow_non_green,
        allow_open_control_dirty=allow_open_control_dirty,
        confirm_tag=confirm_tag,
        no_interactive=no_interactive,
        dry_run=dry_run,
    )

    ctx.console.success(f"PR: {prepared.pr}")
