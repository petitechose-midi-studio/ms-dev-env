from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from ms.core.result import Result
from ms.output.console import ConsoleProtocol
from ms.release.domain.models import ReleaseChannel
from ms.release.errors import ReleaseError
from ms.release.infra.github import workflows as _wf
from ms.release.infra.github.workflows import WorkflowRun

run_process = _wf.run_process
sleep = _wf.sleep
_RUN_LOOKUP_MAX_ATTEMPTS = _wf._RUN_LOOKUP_MAX_ATTEMPTS  # pyright: ignore[reportPrivateUsage]
_RUN_LOOKUP_DELAY_SECONDS = _wf._RUN_LOOKUP_DELAY_SECONDS  # pyright: ignore[reportPrivateUsage]


def _sync_test_patchpoints() -> None:
    _wf.run_process = run_process
    _wf.sleep = sleep
    _wf.uuid4 = uuid4
    _wf._RUN_LOOKUP_MAX_ATTEMPTS = _RUN_LOOKUP_MAX_ATTEMPTS  # pyright: ignore[reportPrivateUsage]
    _wf._RUN_LOOKUP_DELAY_SECONDS = _RUN_LOOKUP_DELAY_SECONDS  # pyright: ignore[reportPrivateUsage]


def dispatch_publish_workflow(
    *,
    workspace_root: Path,
    channel: ReleaseChannel,
    tag: str,
    spec_path: str,
    console: ConsoleProtocol,
    dry_run: bool,
) -> Result[WorkflowRun, ReleaseError]:
    _sync_test_patchpoints()
    return _wf.dispatch_publish_workflow(
        workspace_root=workspace_root,
        channel=channel,
        tag=tag,
        spec_path=spec_path,
        console=console,
        dry_run=dry_run,
    )


def dispatch_app_release_workflow(
    *,
    workspace_root: Path,
    tag: str,
    source_sha: str,
    notes_markdown: str | None,
    notes_source_path: str | None,
    console: ConsoleProtocol,
    dry_run: bool,
) -> Result[WorkflowRun, ReleaseError]:
    _sync_test_patchpoints()
    return _wf.dispatch_app_release_workflow(
        workspace_root=workspace_root,
        tag=tag,
        source_sha=source_sha,
        notes_markdown=notes_markdown,
        notes_source_path=notes_source_path,
        console=console,
        dry_run=dry_run,
    )


def dispatch_app_candidate_workflow(
    *,
    workspace_root: Path,
    source_sha: str,
    console: ConsoleProtocol,
    dry_run: bool,
) -> Result[WorkflowRun, ReleaseError]:
    _sync_test_patchpoints()
    return _wf.dispatch_app_candidate_workflow(
        workspace_root=workspace_root,
        source_sha=source_sha,
        console=console,
        dry_run=dry_run,
    )


def watch_run(
    *,
    workspace_root: Path,
    run_id: int,
    repo_slug: str,
    console: ConsoleProtocol,
    dry_run: bool,
) -> Result[None, ReleaseError]:
    _sync_test_patchpoints()
    return _wf.watch_run(
        workspace_root=workspace_root,
        run_id=run_id,
        repo_slug=repo_slug,
        console=console,
        dry_run=dry_run,
    )


__all__ = [
    "WorkflowRun",
    "dispatch_app_candidate_workflow",
    "dispatch_app_release_workflow",
    "dispatch_publish_workflow",
    "watch_run",
]
