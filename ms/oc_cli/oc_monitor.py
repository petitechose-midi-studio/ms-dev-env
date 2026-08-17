"""oc-monitor (Python).

Build, upload, then attach a PlatformIO serial monitor.
"""

from __future__ import annotations

import subprocess
import time

import typer

from ms.oc_cli.common import (
    build_and_upload,
    kill_monitors,
    prepare_command_context,
    show_results,
    wait_for_serial_port,
)


def _cli(
    env: str | None = typer.Argument(None, help="PlatformIO environment"),
    port: str | None = typer.Option(None, "--port", help="Serial port (optional)"),
) -> None:
    context = prepare_command_context(env)
    console = context.console
    kill_monitors()

    start = time.time()
    status, output = build_and_upload(context, compilation_database=False)

    seconds = int(time.time() - start)
    rc = show_results(
        console,
        output=output,
        project_root=context.project_root,
        env_name=context.env_name,
        status=status,
        seconds=seconds,
    )
    if rc != 0:
        raise typer.Exit(code=rc)

    # Monitor (takes over the terminal)
    if port is None:
        port = wait_for_serial_port(context.pio, env=context.pio_env, timeout_s=5)

    if port:
        console.print(f"Monitor: {port}", style="dim")
        cmd = [*context.pio, "device", "monitor", "-p", port, "--quiet", "--raw"]
    else:
        console.print("Monitor: auto", style="dim")
        cmd = [
            *context.pio,
            "device",
            "monitor",
            "-d",
            str(context.project_root),
            "--quiet",
            "--raw",
        ]
    console.print("---------------------------------", style="dim")
    console.print()

    try:
        proc = subprocess.run(
            cmd,
            cwd=str(context.project_root),
            env=context.pio_env,
            check=False,
        )
        raise typer.Exit(code=proc.returncode)
    except KeyboardInterrupt:
        raise typer.Exit(code=0) from None


def main() -> None:
    typer.run(_cli)


if __name__ == "__main__":
    main()
