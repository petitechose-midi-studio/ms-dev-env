from __future__ import annotations

from pathlib import Path

import typer

from ms.cli.commands.release_app_commands import register_app_commands
from ms.cli.commands.release_common import exit_release, release_error_code
from ms.cli.commands.release_content_commands import register_content_commands
from ms.cli.context import build_context
from ms.cli.release_guided import run_guided_release
from ms.core.result import Err

release_app = typer.Typer(
    add_completion=False,
    no_args_is_help=False,
    invoke_without_command=True,
    help=(
        "Release orchestration.\n"
        "Prefer `ms release content ...` for distribution/content releases.\n"
        "Top-level commands (`ms release plan|prepare|publish|remove`) are kept for compatibility."
    ),
)

release_content_app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    help="Content release commands (distribution).",
)

release_product_app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    help="Application release commands (ms-manager).",
)


def _run_guided_release(*, notes_file: Path | None, watch: bool, dry_run: bool) -> None:
    ctx = build_context()
    run = run_guided_release(
        workspace_root=ctx.workspace.root,
        console=ctx.console,
        notes_file=notes_file,
        watch=watch,
        dry_run=dry_run,
    )
    if isinstance(run, Err):
        exit_release(run.error.message, code=release_error_code(run.error.kind))


@release_app.callback()
def release_root(  # pyright: ignore[reportUnusedFunction]
    ctx: typer.Context,
    notes_file: Path | None = typer.Option(
        None, "--notes-file", help="Optional markdown notes file"
    ),
    watch: bool = typer.Option(False, "--watch", help="Watch workflow run until completion"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Print actions without mutating"),
) -> None:
    if ctx.invoked_subcommand is not None:
        return
    _run_guided_release(notes_file=notes_file, watch=watch, dry_run=dry_run)


@release_app.command("guided")
def guided_release_cmd(
    notes_file: Path | None = typer.Option(
        None, "--notes-file", help="Optional markdown notes file"
    ),
    watch: bool = typer.Option(False, "--watch", help="Watch workflow run until completion"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Print actions without mutating"),
) -> None:
    """Run guided release workflow (product selector + arrow-key navigation)."""

    _run_guided_release(notes_file=notes_file, watch=watch, dry_run=dry_run)


register_content_commands(top_level=release_app, namespace=release_content_app)
register_app_commands(namespace=release_product_app)

release_app.add_typer(release_content_app, name="content")
release_app.add_typer(release_product_app, name="app")
