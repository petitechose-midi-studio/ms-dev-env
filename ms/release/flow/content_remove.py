from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from ms.core.result import Err, Ok, Result
from ms.output.console import ConsoleProtocol
from ms.release.errors import ReleaseError


def resolve_remove_tags(
    *,
    validate_remove_tags_fn: Callable[..., Result[tuple[str, ...], ReleaseError]],
    tags: list[str],
    force: bool,
) -> Result[tuple[str, ...], ReleaseError]:
    return validate_remove_tags_fn(tags=tags, force=force)


def remove_content_release_artifacts[ArtifactsT](
    *,
    remove_distribution_artifacts_fn: Callable[..., Result[ArtifactsT, ReleaseError]],
    workspace_root: Path,
    console: ConsoleProtocol,
    tags: tuple[str, ...],
    dry_run: bool,
) -> Result[None, ReleaseError]:
    removed = remove_distribution_artifacts_fn(
        workspace_root=workspace_root,
        console=console,
        tags=tags,
        dry_run=dry_run,
    )
    if isinstance(removed, Err):
        return removed
    return Ok(None)


def remove_content_github_releases(
    *,
    delete_github_releases_fn: Callable[..., Result[None, ReleaseError]],
    workspace_root: Path,
    console: ConsoleProtocol,
    tags: tuple[str, ...],
    ignore_missing: bool,
    dry_run: bool,
) -> Result[None, ReleaseError]:
    return delete_github_releases_fn(
        workspace_root=workspace_root,
        console=console,
        tags=tags,
        ignore_missing=ignore_missing,
        dry_run=dry_run,
    )
