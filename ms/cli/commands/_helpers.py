"""Shared helpers for CLI commands."""

from __future__ import annotations

from typing import TYPE_CHECKING

import typer

from ms.core.app import App, resolve
from ms.core.errors import ErrorCode
from ms.core.result import Err, Result
from ms.output.console import Style
from ms.services.hardware import HardwareService

if TYPE_CHECKING:
    from ms.cli.context import CLIContext


def hardware_service_for_app(ctx: CLIContext, app_name: str) -> tuple[App, HardwareService]:
    resolved = resolve(app_name, ctx.workspace.root)
    if isinstance(resolved, Err):
        ctx.console.error(resolved.error.message)
        if resolved.error.available:
            ctx.console.print(f"Available: {', '.join(resolved.error.available)}", Style.DIM)
        raise typer.Exit(code=int(ErrorCode.USER_ERROR))

    return resolved.value, HardwareService(
        workspace=ctx.workspace,
        platform=ctx.platform,
        config=ctx.config,
        console=ctx.console,
    )


def exit_on_error[T, E](
    result: Result[T, E],
    ctx: CLIContext,
    error_code: ErrorCode = ErrorCode.BUILD_ERROR,
) -> None:
    """Exit with error if result is Err, otherwise return.

    This helper reduces boilerplate for the common pattern:
        if isinstance(result, Err):
            ctx.console.error(result.error.message)
            raise typer.Exit(code=int(ErrorCode.BUILD_ERROR))

    Expects error objects to have 'message' and optional 'hint' attributes.
    """
    if isinstance(result, Err):
        error = result.error
        message: str = getattr(error, "message", str(error))
        hint: str | None = getattr(error, "hint", None)
        ctx.console.error(message)
        if hint:
            ctx.console.print(f"hint: {hint}", Style.DIM)
        raise typer.Exit(code=int(error_code))
