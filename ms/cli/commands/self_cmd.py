from __future__ import annotations

from importlib import metadata
from pathlib import Path

import typer

from ms.core.errors import ErrorCode
from ms.core.result import Err, Ok
from ms.core.user_workspace import remember_default_workspace_root
from ms.core.workspace import detect_workspace_info
from ms.output.console import RichConsole, Style
from ms.platform.process import run, run_silent


self_app = typer.Typer(
    no_args_is_help=True,
    help="Install/uninstall the ms CLI globally (uv tool).",
    add_completion=False,
)


def _tool_name_for_current_ms() -> str:
    """Best-effort distribution name for the running `ms` package."""
    try:
        mapping = metadata.packages_distributions()
        dists = mapping.get("ms", [])
        if dists:
            return dists[0]
    except Exception:  # noqa: BLE001
        pass
    return "petitechose-audio-workspace"


@self_app.command("install")
def install(
    editable: bool = typer.Option(
        False,
        "--editable",
        "-e",
        help="Install in editable mode (dev workflow)",
    ),
    update_shell: bool = typer.Option(
        False,
        "--update-shell",
        help="Run `uv tool update-shell` after install",
    ),
    remember_workspace: bool = typer.Option(
        False,
        "--remember-workspace",
        help="Remember the detected workspace as default",
    ),
    dry_run: bool = typer.Option(False, "--dry-run", help="Print commands without executing"),
) -> None:
    """Install `ms` and `oc-*` as global user commands via `uv tool`."""
    console = RichConsole()
    info = detect_workspace_info()
    if isinstance(info, Err):
        console.error(info.error.message)
        console.print("hint: run `ms use <path>` or pass `--workspace <path>`", Style.DIM)
        raise typer.Exit(code=int(ErrorCode.ENV_ERROR))

    root = info.value.workspace.root
    cmd = ["uv", "tool", "install"]
    if editable:
        cmd.append("-e")
    cmd.append(str(root))

    console.print(" ".join(cmd), Style.DIM)
    if dry_run:
        return

    result = run_silent(cmd, cwd=root)
    if isinstance(result, Err):
        console.error(str(result.error))
        raise typer.Exit(code=int(ErrorCode.ENV_ERROR))

    if remember_workspace:
        saved = remember_default_workspace_root(root)
        if isinstance(saved, Err):
            console.error(saved.error.message)
            raise typer.Exit(code=int(ErrorCode.IO_ERROR))
        console.success(f"default workspace set: {root}")

    console.success("installed")

    bin_dir = run(["uv", "tool", "dir", "--bin"], cwd=root)
    if isinstance(bin_dir, Ok) and bin_dir.value.strip():
        console.print(f"uv tool bin: {bin_dir.value.strip()}", Style.DIM)

    if update_shell:
        _update_shell(dry_run=dry_run)
    else:
        console.print("hint: run `uv tool update-shell` and restart your shell", Style.DIM)


def _update_shell(*, dry_run: bool) -> None:
    console = RichConsole()
    cmd = ["uv", "tool", "update-shell"]
    console.print(" ".join(cmd), Style.DIM)
    if dry_run:
        return

    result = run_silent(cmd, cwd=Path.cwd())
    if isinstance(result, Err):
        console.error(str(result.error))
        raise typer.Exit(code=int(ErrorCode.ENV_ERROR))
    console.success("PATH updated (restart your shell)")


@self_app.command("update-shell")
def update_shell() -> None:
    """Ensure the uv tool bin directory is on PATH."""
    _update_shell(dry_run=False)


@self_app.command("uninstall")
def uninstall(
    dry_run: bool = typer.Option(False, "--dry-run", help="Print commands without executing"),
) -> None:
    """Uninstall the global `ms` command (via `uv tool uninstall`)."""
    console = RichConsole()
    name = _tool_name_for_current_ms()
    cmd = ["uv", "tool", "uninstall", name]
    console.print(" ".join(cmd), Style.DIM)
    if dry_run:
        return

    result = run_silent(cmd, cwd=Path.cwd())
    if isinstance(result, Err):
        console.error(str(result.error))
        raise typer.Exit(code=int(ErrorCode.ENV_ERROR))
    console.success("uninstalled")
