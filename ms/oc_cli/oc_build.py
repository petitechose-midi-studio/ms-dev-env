"""oc-build (Python).

Build a PlatformIO project with a small, focused output summary.
"""

from __future__ import annotations

import subprocess
import time

import typer

from ms.core.result import Err
from ms.oc_cli.common import (
    OCPlatform,
    build_pio_env,
    detect_env,
    find_project_root,
    get_console,
    resolve_pio_runtime,
    run_with_spinner,
    show_results,
)


def _cli(
    env: str | None = typer.Argument(None, help="PlatformIO environment"),
    stream: bool = typer.Option(False, "--stream", help="Stream PlatformIO output"),
) -> None:
    console = get_console()
    platform = OCPlatform()

    try:
        project_root = find_project_root()
    except FileNotFoundError as e:
        console.print(f"error: {e}", style="red bold")
        raise typer.Exit(code=1) from e

    pio_runtime = resolve_pio_runtime(project_root)
    if isinstance(pio_runtime, Err):
        console.print(f"error: {pio_runtime.error.message}", style="red bold")
        if pio_runtime.error.hint:
            console.print(f"hint: {pio_runtime.error.hint}", style="dim")
        raise typer.Exit(code=1)
    pio_env = build_pio_env(project_root, platform)
    pio = pio_runtime.value.command()
    env_name = detect_env(project_root, env)

    console.clear()
    console.print(f"{project_root.name}", style="bold")
    console.print(f"{env_name}", style="dim")
    console.print()

    start = time.time()
    command = [*pio, "run", "-e", env_name, "-d", str(project_root)]
    if stream:
        code = subprocess.run(command, cwd=project_root, env=pio_env, check=False).returncode
        out = ""
    else:
        code, out, _ = run_with_spinner(
            "Building",
            command,
            cwd=project_root,
            env=pio_env,
        )

    # Generate compile_commands.json for clangd (best-effort)
    if code == 0:
        subprocess.Popen(
            [*pio, "run", "-e", env_name, "-d", str(project_root), "-t", "compiledb"],
            cwd=str(project_root),
            env=pio_env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    seconds = int(time.time() - start)
    if stream:
        rc = 0 if code == 0 else 1
        console.print(
            f"BUILD {'OK' if rc == 0 else 'FAILED'} {seconds}s",
            style="green bold" if rc == 0 else "red bold",
        )
    else:
        rc = show_results(
            console,
            output=out,
            project_root=project_root,
            env_name=env_name,
            status=code,
            seconds=seconds,
        )
    raise typer.Exit(code=rc)


def main() -> None:
    typer.run(_cli)


if __name__ == "__main__":
    main()
