from __future__ import annotations

import json

import typer

from ms.cli.context import build_context
from ms.core.app import resolve
from ms.core.errors import ErrorCode
from ms.core.result import Err
from ms.git import Repository
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

    source_dirty = not Repository(resolved.value.path).is_clean()
    rows: list[dict[str, str | bool | int | None]] = []
    for profile in result.value:
        artifact = ctx.workspace.bin_dir / app / "teensy" / profile.id / "firmware.hex"
        artifact_ready = artifact.is_file()
        rows.append(
            {
                "id": profile.id,
                "source_path": str(resolved.value.path),
                "artifact_path": str(artifact),
                "artifact_ready": artifact_ready,
                "artifact_built_at_ms": (
                    artifact.stat().st_mtime_ns // 1_000_000 if artifact_ready else None
                ),
                "source_dirty": source_dirty,
            }
        )
    if json_output:
        typer.echo(json.dumps(rows))
        return

    ctx.console.header(f"{app} firmware profiles")
    for row in rows:
        ctx.console.print(f"- {row['id']}")
