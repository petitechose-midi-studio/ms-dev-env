"""Web command - build WASM and serve via HTTP."""

from __future__ import annotations

import typer

from ms.cli.context import build_context
from ms.core.config import CONTROLLER_CORE_NATIVE_PORT
from ms.services.build import BuildService


def web(
    app: str = typer.Argument(..., help="App name (e.g. core, bitwig)"),
    port: int = typer.Option(
        CONTROLLER_CORE_NATIVE_PORT,
        "--port",
        help="HTTP port",
        show_default=True,
    ),
) -> None:
    """Build WASM and serve via HTTP."""
    ctx = build_context()
    build_svc = BuildService(
        workspace=ctx.workspace,
        platform=ctx.platform,
        config=ctx.config,
        console=ctx.console,
    )
    raise typer.Exit(code=build_svc.serve_wasm(app_name=app, port=port))
