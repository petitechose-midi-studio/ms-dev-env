"""Run command - build and run native simulator."""

from __future__ import annotations

import typer

from ms.cli.context import build_context
from ms.services.build import BuildService


def run(
    app: str = typer.Argument(..., help="App name (e.g. core, bitwig)"),
) -> None:
    """Build and run native simulator for an app."""
    ctx = build_context()
    build_svc = BuildService(
        workspace=ctx.workspace,
        platform=ctx.platform,
        config=ctx.config,
        console=ctx.console,
    )
    raise typer.Exit(code=build_svc.run_native(app_name=app))
