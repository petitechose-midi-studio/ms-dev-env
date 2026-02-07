"""oc-upload (Python).

Build and upload a PlatformIO project.
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

    build_code, build_out, _ = run_with_spinner(
        "Building",
        [pio, "run", "-e", env_name, "-d", str(project_root)],
        cwd=project_root,
        env=pio_env,
    )

    output = build_out
    if build_code == 0:
        # Generate compile_commands.json for clangd (best-effort)
        subprocess.Popen(
            [pio, "run", "-e", env_name, "-d", str(project_root), "-t", "compiledb"],
            cwd=str(project_root),
            env=pio_env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

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
    else:
        status = build_code

    seconds = int(time.time() - start)
    rc = show_results(
        console,
        output=output,
        project_root=project_root,
        env_name=env_name,
        status=status,
        seconds=seconds,
    )
    raise typer.Exit(code=rc)


def main() -> None:
    typer.run(_cli)


if __name__ == "__main__":
    main()
