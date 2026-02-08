from __future__ import annotations

from pathlib import Path

import typer

from ms.core.result import Err
from ms.core.user_workspace import forget_default_workspace_root, remember_default_workspace_root
from ms.core.workspace import detect_workspace_info, find_workspace_upward
from ms.output.console import RichConsole


def use(
    path: Path = typer.Argument(Path("."), help="Path within the workspace (default: current dir)"),
) -> None:
    """Remember a default workspace for running `ms` from anywhere."""
    console = RichConsole()
    start = path
    if start.is_file():
        start = start.parent

    try:
        start = start.expanduser().resolve()
    except OSError as e:
        console.error(f"invalid path: {e}")
        raise typer.Exit(code=1) from e

    if not start.exists() or not start.is_dir():
        console.error(f"not a directory: {start}")
        raise typer.Exit(code=1)

    root = find_workspace_upward(start)
    if root is None:
        console.error(f"not inside a workspace (missing .ms-workspace): {start}")
        console.print("hint: run from the workspace root, or pass a path inside it")
        raise typer.Exit(code=1)

    saved = remember_default_workspace_root(root)
    if isinstance(saved, Err):
        console.error(saved.error.message)
        raise typer.Exit(code=1)

    console.success(f"default workspace set: {root}")


def where() -> None:
    """Show the workspace `ms` will use."""
    console = RichConsole()
    info = detect_workspace_info()
    if isinstance(info, Err):
        console.error(info.error.message)
        console.print("hint: run `ms use <path>` or set WORKSPACE_ROOT")
        raise typer.Exit(code=1)

    console.print(f"workspace: {info.value.workspace.root}")
    console.print(f"source: {info.value.source}")


def forget() -> None:
    """Forget the remembered default workspace."""
    console = RichConsole()
    result = forget_default_workspace_root()
    if isinstance(result, Err):
        console.error(result.error.message)
        raise typer.Exit(code=1)

    console.success("default workspace cleared")
