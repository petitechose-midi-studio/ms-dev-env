"""Error presentation utilities.

Centralized error formatting and exit code mapping for consistent UX.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ms.core.errors import ErrorCode
from ms.output.console import Style
from ms.services.build_errors import (
    AppConfigInvalid,
    AppNotFound,
    BuildError,
    CompileFailed,
    ConfigureFailed,
    OutputMissing,
    PrereqMissing,
    SdlAppNotFound,
    ToolMissing,
)

if TYPE_CHECKING:
    from ms.output.console import ConsoleProtocol

__all__ = ["print_build_error", "build_error_exit_code"]


def print_build_error(error: BuildError, console: ConsoleProtocol) -> None:
    """Print build error to console with appropriate formatting."""
    match error:
        case AppNotFound(name=name, available=available):
            console.error(f"Unknown app_name: {name}")
            if available:
                console.print(f"Available: {', '.join(available)}", Style.DIM)
        case SdlAppNotFound(app_name=app_name):
            console.error(f"SDL app not found for app_name: {app_name}")
        case AppConfigInvalid(path=path, reason=reason):
            console.error(f"Invalid app config: {path} ({reason})")
        case ToolMissing(tool_id=tool_id, hint=hint):
            console.error(f"{tool_id}: missing")
            console.print(f"hint: {hint}", Style.DIM)
        case PrereqMissing(name=name, hint=hint):
            console.error(f"{name}: missing")
            console.print(f"hint: {hint}", Style.DIM)
        case ConfigureFailed(returncode=rc):
            console.error(f"cmake configure failed (exit {rc})")
        case CompileFailed(returncode=rc):
            console.error(f"build failed (exit {rc})")
        case OutputMissing(path=path):
            console.error(f"output not found: {path}")


def build_error_exit_code(error: BuildError) -> int:
    """Get exit code for a build error."""
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
    # Fallback for exhaustiveness
    return int(ErrorCode.INTERNAL_ERROR)
