from __future__ import annotations

from pathlib import Path
from shlex import quote

import typer

from ms.core.errors import ErrorCode
from ms.core.result import Err, Ok, Result
from ms.core.user_workspace import remember_default_workspace_root
from ms.core.workspace import detect_workspace_info
from ms.output.console import ConsoleProtocol, RichConsole, Style
from ms.platform.detection import Platform, detect_platform
from ms.platform.files import atomic_write_text
from ms.platform.process import run, run_silent

_UV_TOOL_TIMEOUT_SECONDS = 10 * 60.0
_GLOBAL_COMMANDS = ("ms", "oc-build", "oc-upload", "oc-monitor")


self_app = typer.Typer(
    no_args_is_help=True,
    help="Install/uninstall global launchers for the ms-dev-env CLI.",
    add_completion=False,
)


def _uv_tool_bin_dir(root: Path) -> Result[Path, str]:
    result = run(["uv", "tool", "dir", "--bin"], cwd=root, timeout=_UV_TOOL_TIMEOUT_SECONDS)
    if isinstance(result, Err):
        return Err(result.error.stderr or str(result.error))

    value = result.value.strip()
    if not value:
        return Err("uv did not return a tool bin directory")

    return Ok(Path(value))


def _windows_launcher_content(root: Path, command: str) -> str:
    return (
        "@echo off\r\n"
        "setlocal\r\n"
        'set "UV_EXE=%~dp0uv.exe"\r\n'
        'if not exist "%UV_EXE%" set "UV_EXE=uv.exe"\r\n'
        f'"%UV_EXE%" run --project "{root}" {command} %*\r\n'
        "exit /b %ERRORLEVEL%\r\n"
    )


def _posix_launcher_content(root: Path, command: str) -> str:
    return f'#!/usr/bin/env sh\nexec uv run --project {quote(str(root))} {command} "$@"\n'


def _stale_launcher_paths(bin_dir: Path, command: str, platform: Platform) -> list[Path]:
    paths = [bin_dir / f"{command}.exe"]
    if platform.is_windows:
        paths.append(bin_dir / command)
    else:
        paths.append(bin_dir / f"{command}.cmd")

    return paths


def _installed_launcher_path(bin_dir: Path, command: str, platform: Platform) -> Path:
    return bin_dir / f"{command}.cmd" if platform.is_windows else bin_dir / command


def _remove_stale_launchers(bin_dir: Path, command: str, platform: Platform) -> list[Path]:
    stale_paths = _stale_launcher_paths(bin_dir, command, platform)

    removed: list[Path] = []
    for path in stale_paths:
        try:
            path.unlink()
            removed.append(path)
        except FileNotFoundError:
            pass
    return removed


def _remove_repo_launchers(bin_dir: Path, command: str, platform: Platform) -> list[Path]:
    paths = [_installed_launcher_path(bin_dir, command, platform)]
    paths.extend(_stale_launcher_paths(bin_dir, command, platform))

    removed: list[Path] = []
    seen: set[Path] = set()
    for path in paths:
        if path in seen:
            continue
        seen.add(path)
        try:
            path.unlink()
            removed.append(path)
        except FileNotFoundError:
            pass
    return removed


def _write_launcher(bin_dir: Path, root: Path, command: str, platform: Platform) -> Path:
    bin_dir.mkdir(parents=True, exist_ok=True)
    if platform.is_windows:
        path = bin_dir / f"{command}.cmd"
        atomic_write_text(path, _windows_launcher_content(root, command), encoding="utf-8")
        return path

    path = bin_dir / command
    atomic_write_text(path, _posix_launcher_content(root, command), encoding="utf-8")
    path.chmod(0o755)
    return path


def install_repo_launchers(
    root: Path,
    *,
    dry_run: bool,
    console: ConsoleProtocol,
) -> Result[list[Path], str]:
    bin_dir_result = _uv_tool_bin_dir(root)
    if isinstance(bin_dir_result, Err):
        return bin_dir_result

    bin_dir = bin_dir_result.value
    platform = detect_platform()
    written: list[Path] = []
    console.print(f"uv tool bin: {bin_dir}", Style.DIM)

    for command in _GLOBAL_COMMANDS:
        if dry_run:
            for path in _stale_launcher_paths(bin_dir, command, platform):
                if path.exists():
                    console.print(f"would remove stale launcher: {path}", Style.DIM)
        else:
            for path in _remove_stale_launchers(bin_dir, command, platform):
                console.print(f"removed stale launcher: {path}", Style.DIM)

        target = _installed_launcher_path(bin_dir, command, platform)
        if dry_run:
            console.print(f"would write launcher: {target}", Style.DIM)
            written.append(target)
            continue

        written.append(_write_launcher(bin_dir, root, command, platform))

    return Ok(written)


def uninstall_repo_launchers(
    root: Path,
    *,
    dry_run: bool,
    console: ConsoleProtocol,
) -> Result[list[Path], str]:
    bin_dir_result = _uv_tool_bin_dir(root)
    if isinstance(bin_dir_result, Err):
        return bin_dir_result

    bin_dir = bin_dir_result.value
    platform = detect_platform()
    removed: list[Path] = []
    console.print(f"uv tool bin: {bin_dir}", Style.DIM)

    for command in _GLOBAL_COMMANDS:
        if dry_run:
            for path in [_installed_launcher_path(bin_dir, command, platform)] + (
                _stale_launcher_paths(bin_dir, command, platform)
            ):
                if path.exists():
                    console.print(f"would remove launcher: {path}", Style.DIM)
            continue

        for path in _remove_repo_launchers(bin_dir, command, platform):
            console.print(f"removed launcher: {path}", Style.DIM)
            removed.append(path)

    return Ok(removed)


@self_app.command("install")
def install(
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
    """Install `ms` and `oc-*` as global user commands bound to this repo."""
    console = RichConsole()
    info = detect_workspace_info()
    if isinstance(info, Err):
        console.error(info.error.message)
        console.print("hint: run `ms use <path>` or pass `--workspace <path>`", Style.DIM)
        raise typer.Exit(code=int(ErrorCode.ENV_ERROR))

    root = info.value.workspace.root
    result = install_repo_launchers(root, dry_run=dry_run, console=console)
    if isinstance(result, Err):
        console.error(result.error)
        raise typer.Exit(code=int(ErrorCode.ENV_ERROR))

    if remember_workspace and not dry_run:
        saved = remember_default_workspace_root(root)
        if isinstance(saved, Err):
            console.error(saved.error.message)
            raise typer.Exit(code=int(ErrorCode.IO_ERROR))
        console.success(f"default workspace set: {root}")
    elif remember_workspace:
        console.print(f"would set default workspace: {root}", Style.DIM)

    if dry_run:
        console.success("repo launcher dry-run complete")
    else:
        console.success("installed repo launchers")

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

    result = run_silent(cmd, cwd=Path.cwd(), timeout=_UV_TOOL_TIMEOUT_SECONDS)
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
    """Uninstall the global launchers bound to this repo."""
    console = RichConsole()
    launcher_result = uninstall_repo_launchers(Path.cwd(), dry_run=dry_run, console=console)
    if isinstance(launcher_result, Err):
        console.error(launcher_result.error)
        raise typer.Exit(code=int(ErrorCode.ENV_ERROR))

    if dry_run:
        return
    console.success("uninstalled repo launchers")
