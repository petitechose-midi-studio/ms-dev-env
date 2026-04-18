from __future__ import annotations

from pathlib import Path

import typer

from ms.cli.commands.release_common import (
    ensure_release_permissions_or_exit,
    exit_release,
    print_current_release_user,
)
from ms.cli.context import build_context
from ms.core.errors import ErrorCode
from ms.core.result import Err
from ms.output.console import Style
from ms.release.domain import ReleaseBump, ReleaseChannel
from ms.release.flow.content_plan import plan_release
from ms.release.flow.content_preflight import load_open_control_report
from ms.release.flow.permissions import ensure_release_permissions
from ms.release.resolve.plan_io import PlanInput, write_plan_file
from ms.release.view.content_console import (
    print_content_plan,
    print_content_replay,
    print_open_control_preflight,
)

from .release_content_common import resolve_pinned_or_exit


def plan_cmd(
    channel: ReleaseChannel = typer.Option(..., "--channel", help="stable or beta"),
    bump: ReleaseBump = typer.Option("patch", "--bump", help="major/minor/patch"),
    tag: str | None = typer.Option(None, "--tag", help="Override tag"),
    auto: bool = typer.Option(False, "--auto", help="Auto-select pins (strict)"),
    repo: list[str] = typer.Option([], "--repo", help="Override repo SHA (id=sha)"),
    ref: list[str] = typer.Option([], "--ref", help="Override repo ref (id=ref)"),
    allow_non_green: bool = typer.Option(False, "--allow-non-green", help="Allow non-green SHAs"),
    allow_open_control_dirty: bool = typer.Option(
        False,
        "--allow-open-control-dirty",
        help="Allow dirty open-control repos (dev symlink drift)",
    ),
    no_interactive: bool = typer.Option(
        False, "--no-interactive", help="Require explicit --repo overrides"
    ),
    out: Path | None = typer.Option(None, "--out", help="Write plan JSON to file"),
) -> None:
    """Plan a release (no side effects)."""
    ctx = build_context()

    ensure_release_permissions_or_exit(
        workspace_root=ctx.workspace.root,
        console=ctx.console,
        permission_check=ensure_release_permissions,
        require_write=False,
        failure_code=ErrorCode.ENV_ERROR,
    )
    print_current_release_user(workspace_root=ctx.workspace.root, console=ctx.console)

    pinned = resolve_pinned_or_exit(
        workspace_root=ctx.workspace.root,
        console=ctx.console,
        channel=channel,
        repo_overrides=repo,
        ref_overrides=ref,
        auto=auto,
        allow_non_green=allow_non_green,
        interactive=not no_interactive,
    )

    report = load_open_control_report(
        workspace_root=ctx.workspace.root,
        pinned=pinned,
    )
    if report is not None:
        print_open_control_preflight(console=ctx.console, report=report)
    if report is not None and report.dirty_repos() and not allow_open_control_dirty:
        ctx.console.print(
            "warning: open-control has uncommitted changes; "
            "dev symlink tests may not reflect release builds",
            Style.DIM,
        )

    plan_r = plan_release(
        workspace_root=ctx.workspace.root,
        channel=channel,
        bump=bump,
        tag_override=tag,
        pinned=pinned,
    )
    if isinstance(plan_r, Err):
        exit_release(plan_r.error.message, code=ErrorCode.USER_ERROR)

    print_content_plan(plan=plan_r.value, console=ctx.console)

    if out is not None:
        plan_file = write_plan_file(
            path=out,
            plan=PlanInput(
                product="content",
                channel=plan_r.value.channel,
                tag=plan_r.value.tag,
                pinned=plan_r.value.pinned,
                tooling=plan_r.value.tooling,
            ),
        )
        if isinstance(plan_file, Err):
            exit_release(plan_file.error.message, code=ErrorCode.IO_ERROR)
        ctx.console.success(str(out))

    print_content_replay(plan=plan_r.value, console=ctx.console, plan_file=out)
