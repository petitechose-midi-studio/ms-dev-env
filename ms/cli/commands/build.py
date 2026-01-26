from __future__ import annotations

from typing import Literal

import typer

from ms.cli.context import build_context
from ms.core.errors import ErrorCode
from ms.core.result import Err, Ok
from ms.output.console import Style
from ms.services.build import (
    AppConfigInvalid,
    BuildError,
    BuildService,
    AppNotFound,
    CompileFailed,
    ConfigureFailed,
    OutputMissing,
    PrereqMissing,
    SdlAppNotFound,
    ToolMissing,
)

VALID_TARGETS = ("native", "wasm")


def _validate_target(target: str, ctx: object) -> Literal["native", "wasm"] | None:
    """Validate target argument, return None if invalid."""
    if target in VALID_TARGETS:
        return target  # type: ignore[return-value]

    ctx.console.error(f"Unknown target: {target}")  # type: ignore[union-attr]
    ctx.console.print(f"Available: {', '.join(VALID_TARGETS)}", Style.DIM)  # type: ignore[union-attr]
    return None


def _print_build_error(error: BuildError, console: object) -> None:
    """Print build error to console."""
    match error:
        case AppNotFound(name=name, available=available):
            console.error(f"Unknown app_name: {name}")  # type: ignore[union-attr]
            if available:
                console.print(f"Available: {', '.join(available)}", Style.DIM)  # type: ignore[union-attr]
        case SdlAppNotFound(app_name=app_name):
            console.error(f"SDL app not found for app_name: {app_name}")  # type: ignore[union-attr]
        case AppConfigInvalid(path=path, reason=reason):
            console.error(f"Invalid app config: {path} ({reason})")  # type: ignore[union-attr]
        case ToolMissing(tool_id=tool_id, hint=hint):
            console.error(f"{tool_id}: missing")  # type: ignore[union-attr]
            console.print(f"hint: {hint}", Style.DIM)  # type: ignore[union-attr]
        case PrereqMissing(name=name, hint=hint):
            console.error(f"{name}: missing")  # type: ignore[union-attr]
            console.print(f"hint: {hint}", Style.DIM)  # type: ignore[union-attr]
        case ConfigureFailed(returncode=rc):
            console.error(f"cmake configure failed (exit {rc})")  # type: ignore[union-attr]
        case CompileFailed(returncode=rc):
            console.error(f"build failed (exit {rc})")  # type: ignore[union-attr]
        case OutputMissing(path=path):
            console.error(f"output not found: {path}")  # type: ignore[union-attr]


def _error_to_exit_code(error: BuildError) -> int:
    """Convert BuildError to exit code."""
    match error:
        case AppNotFound():
            return int(ErrorCode.USER_ERROR)
        case SdlAppNotFound() | AppConfigInvalid():
            return int(ErrorCode.ENV_ERROR)
        case ToolMissing() | PrereqMissing():
            return int(ErrorCode.ENV_ERROR)
        case ConfigureFailed() | CompileFailed():
            return int(ErrorCode.BUILD_ERROR)
        case OutputMissing():
            return int(ErrorCode.IO_ERROR)


def build(
    app_name: str = typer.Argument(..., help="App: core, bitwig, ..."),
    target: str = typer.Argument(..., help="Target: native|wasm"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Print actions without modifying."),
) -> None:
    """Build native or WASM simulator."""
    ctx = build_context()

    # Validate target early with clear error message
    validated_target = _validate_target(target, ctx)
    if validated_target is None:
        raise typer.Exit(code=int(ErrorCode.USER_ERROR))

    service = BuildService(
        workspace=ctx.workspace,
        platform=ctx.platform,
        config=ctx.config,
        console=ctx.console,
    )

    if validated_target == "native":
        result = service.build_native(app_name=app_name, dry_run=dry_run)
    else:  # wasm
        result = service.build_wasm(app_name=app_name, dry_run=dry_run)

    match result:
        case Ok(output_path):
            ctx.console.success(str(output_path))
        case Err(error):
            _print_build_error(error, ctx.console)
            raise typer.Exit(code=_error_to_exit_code(error))


def run(
    app_name: str = typer.Argument(..., help="App: core, bitwig, ..."),
) -> None:
    """Build and run native simulator."""
    ctx = build_context()
    service = BuildService(
        workspace=ctx.workspace,
        platform=ctx.platform,
        config=ctx.config,
        console=ctx.console,
    )
    code = service.run_native(app_name=app_name)
    raise typer.Exit(code=code)


def web(
    app_name: str = typer.Argument(..., help="App: core, bitwig, ..."),
    port: int = typer.Option(8000, "--port", "-p", help="HTTP server port"),
) -> None:
    """Build and serve WASM simulator."""
    ctx = build_context()
    service = BuildService(
        workspace=ctx.workspace,
        platform=ctx.platform,
        config=ctx.config,
        console=ctx.console,
    )
    code = service.serve_wasm(app_name=app_name, port=port)
    raise typer.Exit(code=code)
