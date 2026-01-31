from __future__ import annotations

import os
from pathlib import Path

import typer

from ms import __version__
from ms.cli.commands.bridge import bridge_app
from ms.cli.commands.build_cmd import build
from ms.cli.commands.check import check
from ms.cli.commands.clean import clean
from ms.cli.commands.dist import dist_app
from ms.cli.commands.release_cmd import release_app
from ms.cli.commands.list_cmd import list_apps
from ms.cli.commands.monitor_cmd import monitor
from ms.cli.commands.prereqs import prereqs
from ms.cli.commands.run_cmd import run
from ms.cli.commands.setup import setup
from ms.cli.commands.status import status
from ms.cli.commands.sync import sync
from ms.cli.commands.self_cmd import self_app
from ms.cli.commands.tools import tools
from ms.cli.commands.upload_cmd import upload
from ms.cli.commands.web_cmd import web
from ms.cli.commands.wipe import destroy, wipe
from ms.cli.commands.workspace import forget, use, where
from ms.core.errors import ErrorCode
from ms.core.workspace import is_workspace_root


app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    rich_markup_mode="rich",
)


# Commands
app.command("list")(list_apps)
app.command()(build)
app.command()(run)
app.command()(web)
app.command()(upload)
app.command()(monitor)
app.command()(check)
app.command()(prereqs)
app.command()(setup)
app.command()(sync)
app.command()(tools)
app.command()(status)
app.command()(clean)
app.command()(use)
app.command()(where)
app.command()(forget)
app.command()(wipe)
app.command()(destroy)

# Sub-apps
app.add_typer(self_app, name="self")
app.add_typer(bridge_app, name="bridge")
app.add_typer(dist_app, name="dist")
app.add_typer(release_app, name="release")


@app.callback()
def _main(  # pyright: ignore[reportUnusedFunction]
    version: bool = typer.Option(False, "--version", help="Show version and exit."),
    workspace: Path | None = typer.Option(
        None,
        "--workspace",
        help="Workspace root (overrides auto detection)",
    ),
) -> None:
    if version:
        typer.echo(__version__)
        raise typer.Exit(code=0)

    if workspace is not None:
        try:
            root = workspace.expanduser().resolve()
        except OSError as e:
            typer.echo(f"error: invalid --workspace: {e}", err=True)
            raise typer.Exit(code=int(ErrorCode.USER_ERROR))

        if not root.is_dir() or not is_workspace_root(root):
            typer.echo(
                f"error: --workspace '{root}' is not a valid workspace (missing .ms-workspace)",
                err=True,
            )
            raise typer.Exit(code=int(ErrorCode.ENV_ERROR))

        os.environ["WORKSPACE_ROOT"] = str(root)


def main() -> None:
    app()
