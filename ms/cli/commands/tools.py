from __future__ import annotations

import typer

from ms.cli.context import build_context
from ms.core.errors import ErrorCode
from ms.services.toolchains import ToolchainService


tools_app = typer.Typer(no_args_is_help=True)


@tools_app.command("sync")
def sync(
    dry_run: bool = typer.Option(False, "--dry-run", help="Print actions without modifying."),
    force: bool = typer.Option(
        False,
        "--force",
        help="Reinstall pinned toolchains even if already installed.",
    ),
) -> None:
    """Install/update dev toolchains into tools/."""
    ctx = build_context()
    service = ToolchainService(
        workspace=ctx.workspace,
        platform=ctx.platform,
        config=ctx.config,
        console=ctx.console,
    )
    ok = service.sync_dev(dry_run=dry_run, force=force)
    if not ok:
        raise typer.Exit(code=int(ErrorCode.ENV_ERROR))
