"""oc-monitor (Python).

Build, upload, then attach a PlatformIO serial monitor.
"""

from __future__ import annotations

import subprocess
import time

import typer

from ms.oc_cli.common import (
    OCPlatform,
    build_pio_env,
    detect_env,
    find_project_root,
    get_console,
    kill_monitors,
    run_with_spinner,
    show_results,
    wait_for_serial_port,
)


def _cli(
    env: str | None = typer.Argument(None, help="PlatformIO environment"),
    port: str | None = typer.Option(None, "--port", help="Serial port (optional)"),
) -> None:
    console = get_console()
    platform = OCPlatform()

    try:
        project_root = find_project_root()
    except FileNotFoundError as e:
        console.print(f"error: {e}", style="red bold")
        raise typer.Exit(code=1) from e

    kill_monitors(platform)

    pio_env = build_pio_env(project_root, platform)
    pio = pio_env.get("PIO", "pio")
    env_name = detect_env(project_root, env)

    console.clear()
    console.print(f"{project_root.name}", style="bold")
    console.print(f"{env_name}", style="dim")
    console.print()

    start = time.time()
    build_code, build_out, _ = run_with_spinner(
        "Building",
        [pio, "run", "-e", env_name, "-d", str(project_root)],
        cwd=project_root,
        env=pio_env,
    )

    output = build_out
    status = build_code
    if build_code == 0:
        up_code, up_out, _ = run_with_spinner(
            "Uploading",
            [
                pio,
                "run",
                "-e",
                env_name,
                "-d",
                str(project_root),
                "-t",
                "nobuild",
                "-t",
                "upload",
            ],
            cwd=project_root,
            env=pio_env,
        )
        output += "\n" + up_out
        status = up_code

    seconds = int(time.time() - start)
    rc = show_results(
        console,
        output=output,
        project_root=project_root,
        env_name=env_name,
        status=status,
        seconds=seconds,
    )
    if rc != 0:
        raise typer.Exit(code=rc)

    # Monitor (takes over the terminal)
    if port is None:
        port = wait_for_serial_port(pio, env=pio_env, timeout_s=5)

    if port:
        console.print(f"Monitor: {port}", style="dim")
        cmd = [pio, "device", "monitor", "-p", port, "--quiet", "--raw"]
    else:
        console.print("Monitor: auto", style="dim")
        cmd = [pio, "device", "monitor", "-d", str(project_root), "--quiet", "--raw"]
    console.print("---------------------------------", style="dim")
    console.print()

    try:
        proc = subprocess.run(cmd, cwd=str(project_root), env=pio_env, check=False)
        raise typer.Exit(code=proc.returncode)
    except KeyboardInterrupt:
        raise typer.Exit(code=0) from None


def main() -> None:
    typer.run(_cli)


if __name__ == "__main__":
    main()
