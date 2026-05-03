from __future__ import annotations

import typer

from ms.cli.commands.release_common import exit_release, release_error_code
from ms.cli.context import build_context
from ms.cli.release_guided_dependencies import run_dependencies_release
from ms.core.result import Err


def register_dependencies_commands(*, namespace: typer.Typer) -> None:
    namespace.command("dependencies")(dependencies_cmd)


def dependencies_cmd(
    promote: bool = typer.Option(
        False,
        "--promote",
        help="Create, validate, and merge the core dependency promotion PR.",
    ),
    watch: bool = typer.Option(
        False,
        "--watch",
        help="Watch the release-alignment workflow after promotion.",
    ),
    dry_run: bool = typer.Option(False, "--dry-run", help="Print actions without mutating."),
) -> None:
    """Check pushed dependency heads and optionally promote core dependency pins."""

    ctx = build_context()
    run = run_dependencies_release(
        workspace_root=ctx.workspace.root,
        console=ctx.console,
        notes_file=None,
        watch=watch,
        dry_run=dry_run,
        promote=promote,
        interactive=False,
    )
    if isinstance(run, Err):
        exit_release(run.error.pretty(), code=release_error_code(run.error.kind))
