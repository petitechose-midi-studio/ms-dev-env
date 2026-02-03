"""Sync command - repos and tools synchronization."""

from __future__ import annotations

import typer

from ms.cli.context import build_context
from ms.core.errors import ErrorCode
from ms.core.result import Err, Ok
from ms.output.console import Style
from ms.services.repos import RepoService
from ms.services.repo_profiles import RepoProfile, repo_manifest_path
from ms.services.toolchains import ToolchainService


def sync(
    tools: bool = typer.Option(False, "--tools", help="Sync tools only"),
    repos: bool = typer.Option(False, "--repos", help="Sync repos only"),
    profile: RepoProfile = typer.Option(
        RepoProfile.dev,
        "--profile",
        help="Repo profile (dev | maintainer)",
    ),
    dry_run: bool = typer.Option(False, "--dry-run", help="Print actions without modifying"),
) -> None:
    """Sync repos and/or tools."""
    ctx = build_context()
    sync_all = not tools and not repos

    if sync_all or repos:
        ctx.console.header("Repos")
        manifest_path = repo_manifest_path(profile)
        result = RepoService(
            workspace=ctx.workspace,
            console=ctx.console,
            manifest_path=manifest_path,
        ).sync_all(dry_run=dry_run)
        match result:
            case Err(e):
                ctx.console.error(e.message)
                if e.hint:
                    ctx.console.print(f"hint: {e.hint}", Style.DIM)
                raise typer.Exit(code=int(ErrorCode.ENV_ERROR))
            case Ok(_):
                pass

    if sync_all or tools:
        ctx.console.header("Tools")
        result = ToolchainService(
            workspace=ctx.workspace,
            platform=ctx.platform,
            config=ctx.config,
            console=ctx.console,
        ).sync_dev(dry_run=dry_run)
        match result:
            case Err(e):
                ctx.console.error(e.message)
                raise typer.Exit(code=int(ErrorCode.ENV_ERROR))
            case Ok(_):
                pass
