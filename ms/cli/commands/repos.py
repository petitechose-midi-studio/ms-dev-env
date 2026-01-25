from __future__ import annotations

import typer

from ms.cli.context import build_context
from ms.core.errors import ErrorCode
from ms.services.repos import RepoService


repos_app = typer.Typer(no_args_is_help=True)


@repos_app.command("sync")
def sync(
    limit: int = typer.Option(200, "--limit", help="Max repos per org."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Print actions without modifying."),
) -> None:
    """Clone/update all repos from GitHub orgs."""
    ctx = build_context()
    service = RepoService(workspace=ctx.workspace, console=ctx.console)
    ok = service.sync_all(limit=limit, dry_run=dry_run)
    if not ok:
        raise typer.Exit(code=int(ErrorCode.ENV_ERROR))
