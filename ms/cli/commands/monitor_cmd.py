"""Monitor command - build + upload + monitor Teensy firmware."""

from __future__ import annotations

import typer

from ms.cli.commands._helpers import hardware_service_for_app
from ms.cli.context import build_context


def monitor(
    app: str = typer.Argument(..., help="App name (e.g. core, bitwig)"),
    env: str | None = typer.Option(
        None, "--env", help="PlatformIO env (e.g. dev, release)", show_default=False
    ),
) -> None:
    """Build, upload, and monitor firmware."""
    ctx = build_context()

    app_obj, hw = hardware_service_for_app(ctx, app)
    raise typer.Exit(code=hw.monitor(app_obj, env=env))
