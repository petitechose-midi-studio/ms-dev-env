"""Tools command - list installed tools."""

from __future__ import annotations

from ms.cli.context import build_context
from ms.output.console import Style
from ms.tools.state import load_state


def tools() -> None:
    """List installed tools."""
    ctx = build_context()
    state = load_state(ctx.workspace.tools_dir)

    if not state:
        ctx.console.print("No tools installed", Style.DIM)
        ctx.console.print("hint: Run: uv run ms sync --tools", Style.DIM)
        return

    for tool_id, tool_state in sorted(state.items()):
        ctx.console.print(f"{tool_id}: {tool_state.version}")
