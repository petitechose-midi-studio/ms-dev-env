from __future__ import annotations

from pathlib import Path

from ms.core.result import Err, Ok, Result
from ms.output.console import ConsoleProtocol
from ms.release.domain import config
from ms.release.domain.models import ReleasePlan
from ms.release.errors import ReleaseError
from ms.release.flow.remote_coherence import assert_release_remote_coherence
from ms.release.infra.github.run_watch import watch_run
from ms.release.infra.github.workflows import dispatch_publish_workflow


def publish_distribution_release(
    *,
    workspace_root: Path,
    console: ConsoleProtocol,
    plan: ReleasePlan,
    watch: bool,
    dry_run: bool,
    remote_coherence_checked: bool = False,
) -> Result[str, ReleaseError]:
    if not remote_coherence_checked:
        coherence = assert_release_remote_coherence(
            workspace_root=workspace_root,
            console=console,
            pinned=plan.pinned,
            tooling=plan.tooling,
            dry_run=dry_run,
        )
        if isinstance(coherence, Err):
            return coherence

    run = dispatch_publish_workflow(
        workspace_root=workspace_root,
        channel=plan.channel,
        tag=plan.tag,
        spec_path=plan.spec_path,
        tooling_sha=plan.tooling.sha,
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
