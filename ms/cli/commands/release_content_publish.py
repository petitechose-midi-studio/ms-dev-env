from __future__ import annotations

from pathlib import Path

import typer

from ms.cli.commands.release_common import ensure_release_permissions_or_exit, exit_release
from ms.cli.context import build_context
from ms.core.errors import ErrorCode
from ms.core.result import Err
from ms.output.console import Style
from ms.release.domain import ReleaseBump, ReleaseChannel
from ms.release.flow.content_publish import publish_distribution_release
from ms.release.flow.permissions import ensure_release_permissions

from .release_content_prepare import prepare_content_release


def publish_cmd(
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
    watch: bool = typer.Option(False, "--watch", help="Watch workflow run until completion"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Print actions without mutating"),
) -> None:
    """Prepare spec PR + dispatch the Publish workflow (approval remains manual)."""
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

    ctx.console.success(f"PR merged: {prepared.pr}")

    run = publish_distribution_release(
        workspace_root=ctx.workspace.root,
        console=ctx.console,
        plan=prepared.plan,
        watch=watch,
        dry_run=dry_run,
    )
    if isinstance(run, Err):
        exit_release(run.error.message, code=ErrorCode.NETWORK_ERROR)

    ctx.console.success(f"Workflow run: {run.value}")
    ctx.console.print(
        "Next: approve the 'release' environment in GitHub Actions to sign + publish.",
        Style.DIM,
    )
