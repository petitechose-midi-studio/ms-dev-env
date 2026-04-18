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
from ms.release.domain import ReleaseBump, ReleaseChannel
from ms.release.flow.app_plan import plan_app_release
from ms.release.flow.permissions import ensure_app_release_permissions
from ms.release.resolve.plan_io import PlanInput, write_plan_file
from ms.release.view.app_console import print_app_plan, print_app_replay

from .release_app_common import resolve_app_pinned_or_exit


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

    pinned = resolve_app_pinned_or_exit(
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

    print_app_plan(plan=planned.value, console=ctx.console)

    if out is not None:
        plan_file = write_plan_file(
            path=out,
            plan=PlanInput(
                product="app",
                channel=planned.value.channel,
                tag=planned.value.tag,
                pinned=planned.value.pinned,
                tooling=planned.value.tooling,
            ),
        )
        if isinstance(plan_file, Err):
            exit_release(plan_file.error.message, code=ErrorCode.IO_ERROR)
        ctx.console.success(str(out))

    print_app_replay(plan=planned.value, console=ctx.console, plan_file=out)
