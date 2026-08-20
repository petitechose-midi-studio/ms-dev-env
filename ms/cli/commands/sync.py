"""Sync command - repos and tools synchronization."""

from __future__ import annotations

import typer

from ms.cli.context import build_context
from ms.core.errors import ErrorCode
from ms.core.result import Err
from ms.output.console import Style
from ms.services.repo_profiles import RepoProfile, repo_manifest_paths
from ms.services.repos import RepoService
from ms.services.toolchains import ToolchainService


def sync(
    tools: bool = typer.Option(False, "--tools", help="Sync tools only"),
    test_tools: bool = typer.Option(False, "--test-tools", help="Sync unit-test tools only"),
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
    sync_all = not tools and not test_tools and not repos

    if sync_all or repos:
        ctx.console.header("Repos")
        result = RepoService(
            workspace=ctx.workspace,
            console=ctx.console,
            manifest_paths=repo_manifest_paths(profile),
            platform=ctx.platform.platform,
        ).sync_all(dry_run=dry_run)
        if isinstance(result, Err):
            ctx.console.error(result.error.message)
            if result.error.hint:
                ctx.console.print(f"hint: {result.error.hint}", Style.DIM)
            raise typer.Exit(code=int(ErrorCode.ENV_ERROR))

    if test_tools:
        ctx.console.header("Test Tools")
        result = ToolchainService(
            workspace=ctx.workspace,
            platform=ctx.platform,
            config=ctx.config,
            console=ctx.console,
        ).sync_unit_tests(dry_run=dry_run)
        if isinstance(result, Err):
            ctx.console.error(result.error.message)
            raise typer.Exit(code=int(ErrorCode.ENV_ERROR))

    if sync_all or tools:
        ctx.console.header("Tools")
        result = ToolchainService(
            workspace=ctx.workspace,
            platform=ctx.platform,
            config=ctx.config,
            console=ctx.console,
        ).sync_dev(dry_run=dry_run)
        if isinstance(result, Err):
            ctx.console.error(result.error.message)
            raise typer.Exit(code=int(ErrorCode.ENV_ERROR))
