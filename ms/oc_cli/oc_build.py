"""oc-build (Python).

Build a PlatformIO project with a small, focused output summary.
"""

from __future__ import annotations

import subprocess
import time

import typer

from ms.oc_cli.common import (
    launch_compilation_database,
    prepare_command_context,
    run_with_spinner,
    show_results,
)


def _cli(
    env: str | None = typer.Argument(None, help="PlatformIO environment"),
    stream: bool = typer.Option(False, "--stream", help="Stream PlatformIO output"),
) -> None:
    context = prepare_command_context(env)
    console = context.console

    start = time.time()
    command = context.run_command()
    if stream:
        code = subprocess.run(
            command,
            cwd=context.project_root,
            env=context.pio_env,
            check=False,
        ).returncode
        out = ""
    else:
        code, out, _ = run_with_spinner(
            "Building",
            command,
            cwd=context.project_root,
            env=context.pio_env,
        )

    # Generate compile_commands.json for clangd (best-effort)
    if code == 0:
        launch_compilation_database(context)

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
            project_root=context.project_root,
            env_name=context.env_name,
            status=code,
            seconds=seconds,
        )
    raise typer.Exit(code=rc)


def main() -> None:
    typer.run(_cli)


if __name__ == "__main__":
    main()
