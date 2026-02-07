"""Workspace cleanup commands.

These are end-user oriented and intentionally conservative by default.
"""

from __future__ import annotations

import os
import shutil
import stat
from collections.abc import Callable
from pathlib import Path

import typer
from rich.console import Console

from ms.cli.context import build_context

_console = Console()


def _remove_readonly(_func: Callable[[str], object], path: str, exc: BaseException) -> None:
    if isinstance(exc, PermissionError):
        os.chmod(path, stat.S_IWRITE)
        os.unlink(path)
    else:
        raise exc


def wipe(
    yes: bool = typer.Option(False, "--yes", "-y", help="Execute (default is dry-run)"),
) -> None:
    """Delete generated workspace artifacts (.ms/, tools/, bin/, .build/)."""
    ctx = build_context()
    ws = ctx.workspace

    dirs: list[Path] = [ws.state_dir, ws.tools_dir, ws.bin_dir, ws.build_dir]
    existing = [d for d in dirs if d.exists()]

    if not existing:
        _console.print("[dim]Nothing to wipe[/dim]")
        return

    if yes:
        _console.print("\n[bold red]EXECUTE[/bold red]\n")
    else:
        _console.print("\n[yellow]DRY-RUN[/yellow]\n")

    for d in existing:
        _console.print(f"  {d}", style="dim")

    if not yes:
        _console.print("\n[dim]Use -y to execute[/dim]")
        return

    for d in existing:
        shutil.rmtree(d, onexc=_remove_readonly)
    _console.print(f"\n[green]Removed {len(existing)} directories[/green]")


def destroy(
    yes: bool = typer.Option(False, "--yes", "-y", help="Execute (default is dry-run)"),
) -> None:
    """Delete the entire workspace directory. Dry-run by default, use -y to execute."""
    ctx = build_context()
    ws = ctx.workspace

    root = ws.root
    if yes:
        _console.print("\n[bold red]EXECUTE[/bold red]\n")
    else:
        _console.print("\n[yellow]DRY-RUN[/yellow]\n")

    _console.print(f"  {root}", style="dim")

    if not yes:
        _console.print("\n[dim]Use -y to execute[/dim]")
        return

    # Safety: require the marker file
    if not (root / ".ms-workspace").is_file():
        _console.print("\n[red bold]error:[/red bold] not a workspace (missing .ms-workspace)")
        raise typer.Exit(code=2)

    shutil.rmtree(root, onexc=_remove_readonly)
    _console.print("\n[green]Workspace deleted[/green]")
