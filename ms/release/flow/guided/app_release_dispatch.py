from __future__ import annotations

from pathlib import Path

from ms.core.result import Err, Ok, Result
from ms.output.console import ConsoleProtocol, Style
from ms.release.domain.models import PinnedRepo
from ms.release.errors import ReleaseError

from .app_contracts import AppGuidedDependencies, AppPrepareResultLike
from .sessions import AppReleaseSession


def validate_app_confirm_inputs(
    session: AppReleaseSession,
) -> Result[tuple[str, str, str, str], ReleaseError]:
    if (
        session.tag is None
        or session.version is None
        or session.repo_sha is None
        or session.tooling_sha is None
    ):
        return Err(
            ReleaseError(
                kind="invalid_input",
                message="incomplete release session; missing tag/version/source sha/tooling",
            )
        )
    return Ok((session.tag, session.version, session.repo_sha, session.tooling_sha))


def dispatch_app_release[PrepareT: AppPrepareResultLike](
    *,
    deps: AppGuidedDependencies[PrepareT],
    workspace_root: Path,
    console: ConsoleProtocol,
    watch: bool,
    dry_run: bool,
    session: AppReleaseSession,
    pinned: tuple[PinnedRepo, ...],
    tag: str,
    version: str,
    repo_sha: str,
    tooling_sha: str,
) -> Result[None, ReleaseError]:
    prepared = deps.prepare_app_pr(
        workspace_root=workspace_root,
        console=console,
        tag=tag,
        version=version,
        base_sha=repo_sha,
        pinned=pinned,
        dry_run=dry_run,
    )
    if isinstance(prepared, Err):
        return prepared

    console.success(f"PR merged: {prepared.value.pr}")
    console.print(f"source sha: {prepared.value.source_sha}", Style.DIM)
    deps.print_notes_status(
        console=console,
        notes_markdown=session.notes_markdown,
        notes_path=session.notes_path,
        notes_sha256=session.notes_sha256,
        auto_label="notes: automatic notes only",
    )

    run = deps.publish_app_release(
        workspace_root=workspace_root,
        console=console,
        tag=tag,
        source_sha=prepared.value.source_sha,
        tooling_sha=tooling_sha,
        notes_markdown=session.notes_markdown,
        notes_source_path=session.notes_path,
        watch=watch,
        dry_run=dry_run,
    )
    if isinstance(run, Err):
        return run

    candidate_url, release_url = run.value
    console.success(f"Candidate run: {candidate_url}")
    console.success(f"Release run: {release_url}")
    console.print(
        "Next: approve the 'app-release' environment in GitHub Actions to publish.",
        Style.DIM,
    )

    cleared = deps.clear_session()
    if isinstance(cleared, Err):
        return cleared
    return Ok(None)
