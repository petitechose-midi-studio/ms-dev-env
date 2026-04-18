from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from time import sleep

from ms.core.result import Err, Ok, Result
from ms.output.console import ConsoleProtocol, Style
from ms.release.domain.models import ReleasePlan
from ms.release.errors import ReleaseError
from ms.release.flow.candidate_types import CandidateVerifyRequest
from ms.release.flow.candidate_verify import inspect_candidate_metadata
from ms.release.infra.github.releases import download_release_assets, release_exists_by_tag
from ms.release.infra.github.run_watch import watch_run
from ms.release.infra.github.workflows import dispatch_candidate_workflow

from .content_candidate_planning import plan_content_candidates
from .content_candidate_types import (
    ContentCandidateAssessment,
    ContentCandidateState,
    ContentCandidateTarget,
    EnsuredContentCandidate,
)

_INCOMPLETE_PROBE_ATTEMPTS = 6
_INCOMPLETE_PROBE_DELAY_SECONDS = 5.0


def assess_content_candidates(
    *,
    workspace_root: Path,
    plan: ReleasePlan,
) -> Result[tuple[ContentCandidateAssessment, ...], ReleaseError]:
    planned = plan_content_candidates(
        workspace_root=workspace_root,
        pinned=plan.pinned,
        tooling=plan.tooling,
    )
    if isinstance(planned, Err):
        return planned

    assessments: list[ContentCandidateAssessment] = []
    for target in planned.value:
        ready = _probe_content_candidate(
            workspace_root=workspace_root,
            target=target,
        )
        if isinstance(ready, Err):
            return ready
        assessments.append(ContentCandidateAssessment(target=target, state=ready.value))
    return Ok(tuple(assessments))


def ensure_content_candidates(
    *,
    workspace_root: Path,
    console: ConsoleProtocol,
    plan: ReleasePlan,
    dry_run: bool,
) -> Result[tuple[EnsuredContentCandidate, ...], ReleaseError]:
    planned = plan_content_candidates(
        workspace_root=workspace_root,
        pinned=plan.pinned,
        tooling=plan.tooling,
    )
    if isinstance(planned, Err):
        return planned

    ensured: list[EnsuredContentCandidate] = []
    for target in planned.value:
        ready = _probe_content_candidate(
            workspace_root=workspace_root,
            target=target,
        )
        if isinstance(ready, Err):
            return ready
        if ready.value is ContentCandidateState.READY:
            console.print(f"candidate ready: {target.label}", Style.DIM)
            ensured.append(EnsuredContentCandidate(target=target, ready_on_entry=True, run=None))
            continue

        if ready.value is ContentCandidateState.INCOMPLETE and not dry_run:
            console.print(f"candidate publication incomplete: {target.label}", Style.DIM)
            waited = _wait_for_content_candidate_ready(
                workspace_root=workspace_root,
                target=target,
            )
            if isinstance(waited, Err):
                return waited
            if waited.value is ContentCandidateState.READY:
                console.print(f"candidate ready after retry: {target.label}", Style.DIM)
                ensured.append(
                    EnsuredContentCandidate(target=target, ready_on_entry=True, run=None)
                )
                continue

        console.print(f"candidate build required: {target.label}", Style.DIM)
        dispatched = dispatch_candidate_workflow(
            workspace_root=workspace_root,
            repo_slug=target.repo_slug,
            workflow_file=target.workflow_file,
            ref=target.ref,
            inputs=target.workflow_inputs,
            console=console,
            dry_run=dry_run,
        )
        if isinstance(dispatched, Err):
            return dispatched

        watched = watch_run(
            workspace_root=workspace_root,
            run_id=dispatched.value.id,
            repo_slug=target.repo_slug,
            console=console,
            dry_run=dry_run,
        )
        if isinstance(watched, Err):
            return watched

        if not dry_run:
            confirmed = _probe_content_candidate(
                workspace_root=workspace_root,
                target=target,
            )
            if isinstance(confirmed, Err):
                return confirmed
            if confirmed.value is not ContentCandidateState.READY:
                return Err(
                    ReleaseError(
                        kind="workflow_failed",
                        message=(
                            "candidate still not ready after successful workflow: "
                            f"{target.label}"
                        ),
                        hint=f"{target.candidate_tag} ({confirmed.value})",
                    )
                )

        ensured.append(
            EnsuredContentCandidate(
                target=target,
                ready_on_entry=False,
                run=dispatched.value,
            )
        )

    return Ok(tuple(ensured))


def _probe_content_candidate(
    *,
    workspace_root: Path,
    target: ContentCandidateTarget,
) -> Result[ContentCandidateState, ReleaseError]:
    with TemporaryDirectory(prefix="candidate-probe-") as tmp:
        metadata_dir = Path(tmp) / "metadata"
        downloaded = download_release_assets(
            workspace_root=workspace_root,
            repo=target.repo_slug,
            tag=target.candidate_tag,
            out_dir=metadata_dir,
            patterns=("candidate.json", "checksums.txt", "candidate.json.sig"),
        )
        if isinstance(downloaded, Err):
            if downloaded.error.kind == "artifact_missing":
                exists = release_exists_by_tag(
                    workspace_root=workspace_root,
                    repo=target.repo_slug,
                    tag=target.candidate_tag,
                )
                if isinstance(exists, Err):
                    return exists
                if exists.value:
                    return Ok(ContentCandidateState.INCOMPLETE)
                return Ok(ContentCandidateState.MISSING)
            return downloaded
        if not _candidate_metadata_complete(metadata_dir):
            return Ok(ContentCandidateState.INCOMPLETE)

        inspected = inspect_candidate_metadata(
            workspace_root=workspace_root,
            request=CandidateVerifyRequest(
                artifacts_dir=metadata_dir,
                manifest_path=metadata_dir / "candidate.json",
                checksums_path=metadata_dir / "checksums.txt",
                sig_path=metadata_dir / "candidate.json.sig",
                expected_input_repos=target.expected_input_repos,
                public_key_b64=target.public_key_b64,
            ),
        )
        if isinstance(inspected, Err):
            return Err(
                ReleaseError(
                    kind=inspected.error.kind,
                    message=f"candidate invalid: {target.label}",
                    hint=inspected.error.pretty(),
                )
            )
        return Ok(ContentCandidateState.READY)


def _wait_for_content_candidate_ready(
    *,
    workspace_root: Path,
    target: ContentCandidateTarget,
) -> Result[ContentCandidateState, ReleaseError]:
    state = _probe_content_candidate(workspace_root=workspace_root, target=target)
    if isinstance(state, Err):
        return state
    if state.value is not ContentCandidateState.INCOMPLETE:
        return state

    for _ in range(_INCOMPLETE_PROBE_ATTEMPTS - 1):
        sleep(_INCOMPLETE_PROBE_DELAY_SECONDS)
        state = _probe_content_candidate(workspace_root=workspace_root, target=target)
        if isinstance(state, Err):
            return state
        if state.value is not ContentCandidateState.INCOMPLETE:
            return state

    return state


def _candidate_metadata_complete(metadata_dir: Path) -> bool:
    required = (
        metadata_dir / "candidate.json",
        metadata_dir / "checksums.txt",
        metadata_dir / "candidate.json.sig",
    )
    return all(path.is_file() for path in required)
