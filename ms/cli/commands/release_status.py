from __future__ import annotations

from ms.cli.commands.release_common import exit_release, release_error_code
from ms.cli.context import build_context
from ms.core.result import Err
from ms.release.flow.release_status import print_release_status


def release_status_cmd() -> None:
    """Show unfinished guided releases and the exact resume command."""
    ctx = build_context()
    status = print_release_status(
        workspace_root=ctx.workspace.root,
        console=ctx.console,
    )
    if isinstance(status, Err):
        exit_release(status.error.pretty(), code=release_error_code(status.error.kind))
