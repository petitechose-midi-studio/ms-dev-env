"""oc-build (Python).

Build a PlatformIO project with a small, focused output summary.
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
    run_with_spinner,
    show_results,
)


def _cli(env: str | None = typer.Argument(None, help="PlatformIO environment")) -> None:
    console = get_console()
    platform = OCPlatform()

    try:
        project_root = find_project_root()
    except FileNotFoundError as e:
        console.print(f"error: {e}", style="red bold")
        raise typer.Exit(code=1) from e

    pio_env = build_pio_env(project_root, platform)
    pio = pio_env.get("PIO", "pio")
    env_name = detect_env(project_root, env)

    console.clear()
    console.print(f"{project_root.name}", style="bold")
    console.print(f"{env_name}", style="dim")
    console.print()

    start = time.time()
    code, out, _ = run_with_spinner(
        "Building",
        [pio, "run", "-e", env_name, "-d", str(project_root)],
        cwd=project_root,
        env=pio_env,
    )

    # Generate compile_commands.json for clangd (best-effort)
    if code == 0:
        subprocess.Popen(
            [pio, "run", "-e", env_name, "-d", str(project_root), "-t", "compiledb"],
            cwd=str(project_root),
            env=pio_env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    seconds = int(time.time() - start)
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
