"""Build command - build native/wasm/teensy targets."""

from __future__ import annotations

from enum import StrEnum
from pathlib import Path

import typer

from ms.cli.commands._helpers import exit_on_error
from ms.cli.context import build_context
from ms.core.app import resolve
from ms.core.errors import ErrorCode
from ms.core.result import Err, Ok
from ms.output.console import Style
from ms.output.errors import build_error_exit_code, print_build_error
from ms.services.bitwig import BitwigService
from ms.services.build import BuildService
from ms.services.hardware import HardwareService


class Target(StrEnum):
    native = "native"
    wasm = "wasm"
    teensy = "teensy"
    extension = "extension"


def build(
    app: str = typer.Argument(..., help="App name (e.g. core, bitwig)"),
    target: Target = typer.Option(Target.native, "--target", help="Build target"),
    env: str | None = typer.Option(
        None, "--env", help="PlatformIO env (teensy)", show_default=False
    ),
    extensions_dir: Path | None = typer.Option(
        None,
        "--extensions-dir",
        help="Bitwig extensions directory (target=extension)",
        show_default=False,
    ),
    dry_run: bool = typer.Option(False, "--dry-run", help="Print actions without modifying"),
) -> None:
    """Build an app for a target."""
    ctx = build_context()

    if target in (Target.native, Target.wasm):
        build_svc = BuildService(
            workspace=ctx.workspace,
            platform=ctx.platform,
            config=ctx.config,
            console=ctx.console,
        )

        result = (
            build_svc.build_native(app_name=app, dry_run=dry_run)
            if target == Target.native
            else build_svc.build_wasm(app_name=app, dry_run=dry_run)
        )

        match result:
            case Ok(path):
                ctx.console.success(str(path))
                return
            case Err(error):
                print_build_error(error, ctx.console)
                raise typer.Exit(code=build_error_exit_code(error))

    if target == Target.extension:
        if app != "bitwig":
            ctx.console.error("target=extension is only supported for app 'bitwig'")
            raise typer.Exit(code=int(ErrorCode.USER_ERROR))

        resolved_extensions_dir: Path | None = None
        if extensions_dir is not None:
            p = extensions_dir.expanduser()
            if not p.is_absolute():
                p = ctx.workspace.root / p
            resolved_extensions_dir = p

        bw = BitwigService(
            workspace=ctx.workspace,
            platform=ctx.platform,
            config=ctx.config,
            console=ctx.console,
        )
        result = bw.deploy(extensions_dir=resolved_extensions_dir, dry_run=dry_run)
        if isinstance(result, Ok):
            ctx.console.success(str(result.value))
            return

        error = result.error
        ctx.console.error(error.message)
        if error.hint:
            ctx.console.print(f"hint: {error.hint}", Style.DIM)

        if error.kind in ("host_missing", "maven_missing", "dir_not_configured"):
            raise typer.Exit(code=int(ErrorCode.ENV_ERROR))
        raise typer.Exit(code=int(ErrorCode.BUILD_ERROR))

    # teensy
    match resolve(app, ctx.workspace.root):
        case Err(e):
            ctx.console.error(e.message)
            if e.available:
                ctx.console.print(f"Available: {', '.join(e.available)}", Style.DIM)
            raise typer.Exit(code=int(ErrorCode.USER_ERROR))
        case Ok(app_obj):
            pass

    hw = HardwareService(
        workspace=ctx.workspace,
        platform=ctx.platform,
        config=ctx.config,
        console=ctx.console,
    )
    exit_on_error(hw.build(app_obj, env=env, dry_run=dry_run), ctx)
