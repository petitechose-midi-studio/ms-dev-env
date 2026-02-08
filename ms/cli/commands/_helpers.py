"""Shared helpers for CLI commands."""

from __future__ import annotations

from typing import TYPE_CHECKING, NoReturn, TypeVar

import typer

from ms.core.errors import ErrorCode
from ms.core.result import Err, Result
from ms.output.console import Style

if TYPE_CHECKING:
    from ms.cli.context import CLIContext


T = TypeVar("T")
E = TypeVar("E")


def exit_on_error[T, E](
    result: Result[T, E],
    ctx: CLIContext,
    error_code: ErrorCode = ErrorCode.BUILD_ERROR,
) -> None:
    """Exit with error if result is Err, otherwise return.

    This helper reduces boilerplate for the common pattern:
        match result:
            case Err(e):
                ctx.console.error(e.message)
                if e.hint:
                    ctx.console.print(f"hint: {e.hint}", Style.DIM)
                raise typer.Exit(code=int(ErrorCode.BUILD_ERROR))
            case Ok(_):
                pass

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


def exit_with_code(code: int) -> NoReturn:
    """Exit with given code. Explicit helper for clarity."""
    raise typer.Exit(code=code)
