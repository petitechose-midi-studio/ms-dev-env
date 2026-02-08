from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from ms.core.result import Err, Ok, Result
from ms.output.console import ConsoleProtocol
from ms.release.domain import config
from ms.release.domain.models import ReleasePlan
from ms.release.errors import ReleaseError
from ms.release.infra.github.workflows import dispatch_publish_workflow, watch_run


def publish_distribution_release(
    *,
    workspace_root: Path,
    console: ConsoleProtocol,
    plan: ReleasePlan,
    watch: bool,
    dry_run: bool,
) -> Result[str, ReleaseError]:
    run = dispatch_publish_workflow(
        workspace_root=workspace_root,
        channel=plan.channel,
        tag=plan.tag,
        spec_path=plan.spec_path,
        console=console,
        dry_run=dry_run,
    )
    if isinstance(run, Err):
        return run

    if watch:
        watched = watch_run(
            workspace_root=workspace_root,
            run_id=run.value.id,
            repo_slug=config.DIST_REPO_SLUG,
            console=console,
            dry_run=dry_run,
        )
        if isinstance(watched, Err):
            return watched

    return Ok(run.value.url)


def publish_content_release(
    *,
    publish_distribution_release_fn: Callable[..., Result[str, ReleaseError]],
    workspace_root: Path,
    console: ConsoleProtocol,
    plan: ReleasePlan,
    watch: bool,
    dry_run: bool,
) -> Result[str, ReleaseError]:
    return publish_distribution_release_fn(
        workspace_root=workspace_root,
        console=console,
        plan=plan,
        watch=watch,
        dry_run=dry_run,
    )
