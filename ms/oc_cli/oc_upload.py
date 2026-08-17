"""oc-upload (Python).

Build and upload a PlatformIO project.
"""

from __future__ import annotations

import time

import typer

from ms.oc_cli.common import (
    build_and_upload,
    prepare_command_context,
    show_results,
)


def _cli(env: str | None = typer.Argument(None, help="PlatformIO environment")) -> None:
    context = prepare_command_context(env)
    console = context.console

    start = time.time()
    status, output = build_and_upload(context, compilation_database=True)

    seconds = int(time.time() - start)
    rc = show_results(
        console,
        output=output,
        project_root=context.project_root,
        env_name=context.env_name,
        status=status,
        seconds=seconds,
    )
    raise typer.Exit(code=rc)


def main() -> None:
    typer.run(_cli)


if __name__ == "__main__":
    main()
