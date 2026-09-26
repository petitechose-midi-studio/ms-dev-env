"""Tools command - list installed tools."""

from __future__ import annotations

import typer

from ms.cli.context import build_context
from ms.core.errors import ErrorCode
from ms.core.result import Err
from ms.output.console import Style
from ms.tools.state import load_state


def tools() -> None:
    """List installed tools."""
    ctx = build_context()
    loaded = load_state(ctx.workspace.tools_dir)
    if isinstance(loaded, Err):
        ctx.console.print(f"error: {loaded.error.message}", Style.ERROR)
        raise typer.Exit(code=int(ErrorCode.IO_ERROR))

    state = loaded.value
    if not state:
        ctx.console.print("No tools installed", Style.DIM)
        ctx.console.print("hint: Run: uv run ms sync --tools", Style.DIM)
        return

    for tool_id, tool_state in sorted(state.items()):
        ctx.console.print(f"{tool_id}: {tool_state.version}")
