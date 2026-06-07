from __future__ import annotations

from pathlib import Path
from typing import NoReturn

import typer

from ms.cli.context import build_context
from ms.core.errors import ErrorCode
from ms.core.result import Err
from ms.output.console import Style
from ms.services.device_fs import (
    DEFAULT_BRIDGE_CONTROL_PORT,
    BridgeControlClient,
    DeviceFileSystemClient,
    normalize_remote_path,
)
from ms.services.device_fs_codec import FsFileType, FsStatus, file_type_label

device_app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    rich_markup_mode="rich",
)
fs_app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    rich_markup_mode="rich",
)


@fs_app.command("stat")
def fs_stat(
    path: str = typer.Argument("/", help="Remote product path on the controller SD filesystem."),
    control_port: int = typer.Option(
        DEFAULT_BRIDGE_CONTROL_PORT,
        "--control-port",
        help="oc-bridge local control port.",
    ),
) -> None:
    """Show metadata for a remote file or directory."""
    ctx = build_context()
    remote = normalize_remote_path(path)
    client = _client(control_port)
    result = client.stat(remote)
    if isinstance(result, Err):
        _exit_device_fs_error(result.error)

    stat = result.value
    if stat.status != FsStatus.OK:
        ctx.console.error(f"stat failed for {remote}: {stat.status.name.lower().replace('_', '-')}")
        raise typer.Exit(code=int(ErrorCode.IO_ERROR))

    ctx.console.print(
        f"{remote}  {file_type_label(stat.file_type)}  {stat.size_bytes} bytes",
        Style.DEFAULT,
    )


@fs_app.command("list")
def fs_list(
    path: str = typer.Argument("/", help="Remote directory path on the controller SD filesystem."),
    control_port: int = typer.Option(
        DEFAULT_BRIDGE_CONTROL_PORT,
        "--control-port",
        help="oc-bridge local control port.",
    ),
) -> None:
    """List a remote directory."""
    ctx = build_context()
    remote = normalize_remote_path(path)
    client = _client(control_port)
    result = client.list(remote)
    if isinstance(result, Err):
        _exit_device_fs_error(result.error)

    ctx.console.print(f"{remote}", Style.BOLD)
    ctx.console.print(f"  {'type':<9} {'size':>10}  name", Style.DIM)
    for entry in result.value:
        size = "-" if entry.file_type == FsFileType.DIRECTORY else str(entry.size_bytes)
        suffix = "..." if entry.name_truncated else ""
        ctx.console.print(
            f"  {file_type_label(entry.file_type):<9} {size:>10}  {entry.name}{suffix}"
        )


@fs_app.command("pull")
def fs_pull(
    remote_path: str = typer.Argument(
        ...,
        help="Remote file path on the controller SD filesystem.",
    ),
    local_path: Path = typer.Argument(..., help="Local destination file."),
    control_port: int = typer.Option(
        DEFAULT_BRIDGE_CONTROL_PORT,
        "--control-port",
        help="oc-bridge local control port.",
    ),
) -> None:
    """Copy a remote file from the controller SD filesystem to the PC."""
    ctx = build_context()
    remote = normalize_remote_path(remote_path)
    client = _client(control_port)
    result = client.pull(remote, local_path)
    if isinstance(result, Err):
        _exit_device_fs_error(result.error)

    ctx.console.success(
        f"pulled {result.value.remote_path} -> {result.value.local_path} "
        f"({result.value.size_bytes} bytes)"
    )


@fs_app.command("push")
def fs_push(
    local_path: Path = typer.Argument(..., help="Local source file."),
    remote_path: str = typer.Argument(..., help="Remote destination path on the controller SD."),
    control_port: int = typer.Option(
        DEFAULT_BRIDGE_CONTROL_PORT,
        "--control-port",
        help="oc-bridge local control port.",
    ),
) -> None:
    """Copy a local file from the PC to the controller SD filesystem."""
    ctx = build_context()
    remote = normalize_remote_path(remote_path)
    client = _client(control_port)
    result = client.push(local_path, remote)
    if isinstance(result, Err):
        _exit_device_fs_error(result.error)

    ctx.console.success(
        f"pushed {result.value.local_path} -> {result.value.remote_path} "
        f"({result.value.size_bytes} bytes)"
    )


def _client(control_port: int) -> DeviceFileSystemClient:
    return DeviceFileSystemClient(BridgeControlClient(port=control_port))


def _exit_device_fs_error(error: object) -> NoReturn:
    message: str = getattr(error, "message", str(error))
    hint: str | None = getattr(error, "hint", None)
    typer.echo(f"error: {message}", err=True)
    if hint:
        typer.echo(f"hint: {hint}", err=True)
    raise typer.Exit(code=int(ErrorCode.IO_ERROR))


device_app.add_typer(
    fs_app,
    name="fs",
    help="Inspect and transfer controller SD filesystem data through oc-bridge.",
)
