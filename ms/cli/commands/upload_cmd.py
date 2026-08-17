"""Upload command - build + upload firmware for Teensy targets."""

from __future__ import annotations

import typer

from ms.cli.commands._helpers import exit_on_error, hardware_service_for_app
from ms.cli.context import build_context


def upload(
    app: str = typer.Argument(..., help="App name (e.g. core, bitwig)"),
    env: str | None = typer.Option(
        None, "--env", help="PlatformIO env (e.g. dev, release)", show_default=False
    ),
    dry_run: bool = typer.Option(False, "--dry-run", help="Print actions without modifying"),
) -> None:
    """Build and upload firmware."""
    ctx = build_context()

    app_obj, hw = hardware_service_for_app(ctx, app)
    exit_on_error(hw.upload(app_obj, env=env, dry_run=dry_run), ctx)
