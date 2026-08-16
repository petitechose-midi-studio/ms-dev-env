from __future__ import annotations

import json

import typer

from ms.cli.context import build_context
from ms.core.app import resolve
from ms.core.errors import ErrorCode
from ms.core.result import Err
from ms.services.hardware import HardwareService


def profiles(
    app: str = typer.Argument(..., help="App name (e.g. core, bitwig)"),
    json_output: bool = typer.Option(False, "--json", help="Emit machine-readable JSON"),
) -> None:
    """List Teensy firmware profiles exposed to development tools."""
    ctx = build_context()
    resolved = resolve(app, ctx.workspace.root)
    if isinstance(resolved, Err):
        ctx.console.error(resolved.error.message)
        raise typer.Exit(code=int(ErrorCode.USER_ERROR))

    result = HardwareService(
        workspace=ctx.workspace,
        platform=ctx.platform,
        config=ctx.config,
        console=ctx.console,
    ).profiles(resolved.value)
    if isinstance(result, Err):
        ctx.console.error(result.error.message)
        raise typer.Exit(code=int(ErrorCode.ENV_ERROR))

    rows = [
        {
            "id": profile.id,
            "label": profile.label,
            "artifact_path": str(
                ctx.workspace.bin_dir / app / "teensy" / profile.id / "firmware.hex"
            ),
        }
        for profile in result.value
    ]
    if json_output:
        typer.echo(json.dumps(rows))
        return

    ctx.console.header(f"{app} firmware profiles")
    for row in rows:
        ctx.console.print(f"- {row['id']}: {row['label']}")
