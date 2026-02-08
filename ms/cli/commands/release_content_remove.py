from __future__ import annotations

import typer

from ms.cli.commands.release_common import ensure_release_permissions_or_exit, exit_release
from ms.cli.context import build_context
from ms.core.errors import ErrorCode
from ms.core.result import Err
from ms.release.flow.content_remove import (
    delete_github_releases,
    remove_distribution_artifacts,
    validate_remove_tags,
)
from ms.release.flow.permissions import ensure_release_permissions


def remove_cmd(
    tag: list[str] = typer.Option([], "--tag", help="Release tag to delete (repeatable)"),
    force: bool = typer.Option(False, "--force", help="Allow deleting stable tags"),
    ignore_missing: bool = typer.Option(False, "--ignore-missing", help="Ignore missing releases"),
    yes: bool = typer.Option(False, "-y", "--yes", help="Skip confirmation prompt"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Print actions without mutating"),
) -> None:
    """Remove releases (cleanup artifacts + delete GitHub Releases)."""
    ctx = build_context()

    ensure_release_permissions_or_exit(
        workspace_root=ctx.workspace.root,
        console=ctx.console,
        permission_check=ensure_release_permissions,
        require_write=True,
        failure_code=ErrorCode.USER_ERROR,
    )

    valid = validate_remove_tags(tags=tag, force=force)
    if isinstance(valid, Err):
        exit_release(valid.error.message, code=ErrorCode.USER_ERROR)
    tags = valid.value

    ctx.console.header("Remove Releases")
    for release_tag in tags:
        ctx.console.print(f"- {release_tag}")
    if not dry_run and not yes:
        typed = typer.prompt("Type DELETE to confirm", default="")
        if typed.strip() != "DELETE":
            exit_release("confirmation mismatch", code=ErrorCode.USER_ERROR)

    artifacts = remove_distribution_artifacts(
        workspace_root=ctx.workspace.root,
        console=ctx.console,
        tags=tags,
        dry_run=dry_run,
    )
    if isinstance(artifacts, Err):
        exit_release(artifacts.error.message, code=ErrorCode.IO_ERROR)

    deleted = delete_github_releases(
        workspace_root=ctx.workspace.root,
        console=ctx.console,
        tags=tags,
        ignore_missing=ignore_missing,
        dry_run=dry_run,
    )
    if isinstance(deleted, Err):
        exit_release(deleted.error.message, code=ErrorCode.NETWORK_ERROR)

    ctx.console.success("done")
