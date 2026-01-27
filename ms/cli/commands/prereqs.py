from __future__ import annotations

import typer

from ms.cli.commands._helpers import exit_on_error
from ms.cli.context import build_context
from ms.core.errors import ErrorCode
from ms.services.prereqs import PrereqsService
from ms.services.toolchains import ToolchainService


def prereqs(
    install: bool = typer.Option(False, "--install", help="Install safe prerequisites"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show what would be done"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Auto-confirm (do not prompt)"),
    skip_repos: bool = typer.Option(False, "--skip-repos", help="Skip repo-sync prerequisites"),
    skip_tools: bool = typer.Option(False, "--skip-tools", help="Skip toolchain prerequisites"),
    skip_python: bool = typer.Option(False, "--skip-python", help="Skip Python/uv prerequisites"),
) -> None:
    """Check prerequisites required for dev setup."""
    ctx = build_context()

    require_git_for_tools = False
    if skip_repos and not skip_tools:
        require_git_for_tools = ToolchainService(
            workspace=ctx.workspace,
            platform=ctx.platform,
            config=ctx.config,
            console=ctx.console,
        ).needs_git_for_sync_dev()

    result = PrereqsService(
        workspace=ctx.workspace,
        platform=ctx.platform,
        config=ctx.config,
        console=ctx.console,
        confirm=lambda msg: typer.confirm(msg, default=False),
    ).ensure(
        require_git=(not skip_repos) or require_git_for_tools,
        require_uv=not skip_python,
        install=install,
        dry_run=dry_run,
        assume_yes=yes,
        fail_if_missing=True,
    )

    exit_on_error(result, ctx, error_code=ErrorCode.ENV_ERROR)
