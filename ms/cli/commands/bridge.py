"""Bridge commands - install/build/run oc-bridge."""

from __future__ import annotations

import typer

from ms.cli.context import build_context
from ms.core.errors import ErrorCode
from ms.core.result import Err, Ok
from ms.output.console import Style
from ms.services.bridge import BridgeService


bridge_app = typer.Typer(
    add_completion=False,
    no_args_is_help=False,
    rich_markup_mode="rich",
)


@bridge_app.callback(invoke_without_command=True)
def bridge(
    ctx: typer.Context,
    build: bool = typer.Option(
        False,
        "--build",
        help="Build oc-bridge from source (requires Rust)",
    ),
) -> None:
    """Run bridge (installs if needed)."""
    if ctx.invoked_subcommand is not None:
        return

    c = build_context()
    service = BridgeService(
        workspace=c.workspace,
        platform=c.platform,
        config=c.config,
        console=c.console,
    )

    if build:
        result = service.build()
    else:
        result = service.install_prebuilt()

    match result:
        case Err(e):
            c.console.error(e.message)
            if e.hint:
                c.console.print(f"hint: {e.hint}", Style.DIM)
            raise typer.Exit(code=int(ErrorCode.ENV_ERROR))
        case Ok(_):
            pass

    code = service.run(args=[])
    raise typer.Exit(code=code)


@bridge_app.command("install")
def install(
    version: str | None = typer.Option(
        None,
        "--version",
        help="Install a specific release version (e.g. 0.1.1)",
    ),
    force: bool = typer.Option(False, "--force", help="Re-download even if installed"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show what would be done"),
) -> None:
    """Install oc-bridge from GitHub releases."""
    c = build_context()
    service = BridgeService(
        workspace=c.workspace,
        platform=c.platform,
        config=c.config,
        console=c.console,
    )

    result = service.install_prebuilt(version=version, force=force, dry_run=dry_run)
    match result:
        case Ok(_):
            return
        case Err(e):
            c.console.error(e.message)
            if e.hint:
                c.console.print(f"hint: {e.hint}", Style.DIM)
            raise typer.Exit(code=int(ErrorCode.ENV_ERROR))


@bridge_app.command("build")
def build_cmd(
    debug: bool = typer.Option(False, "--debug", help="Build debug binary"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show what would be done"),
) -> None:
    """Build oc-bridge from source and install into bin/."""
    c = build_context()
    service = BridgeService(
        workspace=c.workspace,
        platform=c.platform,
        config=c.config,
        console=c.console,
    )

    result = service.build(release=not debug, dry_run=dry_run)
    match result:
        case Ok(_):
            return
        case Err(e):
            c.console.error(e.message)
            if e.hint:
                c.console.print(f"hint: {e.hint}", Style.DIM)
            raise typer.Exit(code=int(ErrorCode.BUILD_ERROR))
