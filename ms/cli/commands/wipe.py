"""Workspace cleanup commands.

These are end-user oriented and intentionally conservative by default.
"""

from __future__ import annotations

from pathlib import Path

import typer

from ms.cli.commands.removal import remove_directories
from ms.cli.context import build_context
from ms.output.console import Style
from ms.platform.files import remove_tree


def wipe(
    yes: bool = typer.Option(False, "--yes", "-y", help="Execute (default is dry-run)"),
) -> None:
    """Delete generated workspace artifacts (.ms/, tools/, bin/, .build/)."""
    ctx = build_context()
    ws = ctx.workspace

    dirs: list[Path] = [ws.state_dir, ws.tools_dir, ws.bin_dir, ws.build_dir]
    remove_directories(dirs, yes=yes, empty_message="Nothing to wipe", console=ctx.console)


def destroy(
    yes: bool = typer.Option(False, "--yes", "-y", help="Execute (default is dry-run)"),
) -> None:
    """Delete the entire workspace directory. Dry-run by default, use -y to execute."""
    ctx = build_context()
    ws = ctx.workspace

    root = ws.root
    ctx.console.newline()
    ctx.console.print("EXECUTE" if yes else "DRY-RUN", Style.ERROR if yes else Style.WARNING)
    ctx.console.newline()
    ctx.console.print(f"  {root}", Style.DIM)

    if not yes:
        ctx.console.newline()
        ctx.console.print("Use -y to execute", Style.DIM)
        return

    # Safety: require the marker file
    if not (root / ".ms-workspace").is_file():
        ctx.console.newline()
        ctx.console.error("not a workspace (missing .ms-workspace)")
        raise typer.Exit(code=2)

    remove_tree(root)
    ctx.console.newline()
    ctx.console.print("Workspace deleted", Style.SUCCESS)
