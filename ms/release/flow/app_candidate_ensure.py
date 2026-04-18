from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from tempfile import TemporaryDirectory
from time import sleep

from ms.core.result import Err, Ok, Result
from ms.output.console import ConsoleProtocol, Style
from ms.release.domain import CandidateInputRepo, config, resolve_trusted_candidate_producer
from ms.release.errors import ReleaseError
from ms.release.flow.candidate_types import CandidateVerifyRequest
from ms.release.flow.candidate_verify import inspect_candidate_metadata
from ms.release.infra.github.releases import download_release_assets, release_exists_by_tag
from ms.release.infra.github.workflows import (
    WorkflowRun,
    dispatch_app_candidate_workflow,
)

_INCOMPLETE_PROBE_ATTEMPTS = 6
_INCOMPLETE_PROBE_DELAY_SECONDS = 5.0


class AppCandidateState(StrEnum):
    READY = "ready"
    MISSING = "missing"
    INCOMPLETE = "incomplete"


@dataclass(frozen=True, slots=True)
class EnsuredAppCandidate:
    candidate_tag: str
    release_url: str
    run: WorkflowRun | None


@dataclass(frozen=True, slots=True)
class AppPublishResult:
    candidate: EnsuredAppCandidate
    release: WorkflowRun


def ensure_app_candidate(
    *,
    workspace_root: Path,
    source_sha: str,
    tooling_sha: str,
    console: ConsoleProtocol,
    dry_run: bool,
) -> Result[EnsuredAppCandidate, ReleaseError]:
    candidate_tag = app_candidate_tag(source_sha=source_sha, tooling_sha=tooling_sha)
    release_url = candidate_release_url(candidate_tag=candidate_tag)

    state = _probe_app_candidate(
        workspace_root=workspace_root,
        source_sha=source_sha,
        tooling_sha=tooling_sha,
    )
    if isinstance(state, Err):
        return state

    if state.value is AppCandidateState.READY:
        console.print(f"candidate ready: {candidate_tag}", Style.DIM)
        return Ok(
            EnsuredAppCandidate(
                candidate_tag=candidate_tag,
                release_url=release_url,
                run=None,
            )
        )

    if state.value is AppCandidateState.INCOMPLETE and not dry_run:
        console.print(f"candidate publication incomplete: {candidate_tag}", Style.DIM)
        waited = _wait_for_app_candidate_ready(
            workspace_root=workspace_root,
            source_sha=source_sha,
            tooling_sha=tooling_sha,
        )
        if isinstance(waited, Err):
            return waited
        if waited.value is AppCandidateState.READY:
            console.print(f"candidate ready after retry: {candidate_tag}", Style.DIM)
            return Ok(
                EnsuredAppCandidate(
                    candidate_tag=candidate_tag,
                    release_url=release_url,
                    run=None,
                )
            )

    console.print(f"candidate build required: {candidate_tag}", Style.DIM)
    dispatched = dispatch_app_candidate_workflow(
        workspace_root=workspace_root,
        source_sha=source_sha,
        tooling_sha=tooling_sha,
        console=console,
        dry_run=dry_run,
    )
    if isinstance(dispatched, Err):
        return dispatched

    return Ok(
        EnsuredAppCandidate(
            candidate_tag=candidate_tag,
            release_url=release_url,
            run=dispatched.value,
        )
    )


def _probe_app_candidate(
    *,
    workspace_root: Path,
    source_sha: str,
    tooling_sha: str,
) -> Result[AppCandidateState, ReleaseError]:
    candidate_tag = app_candidate_tag(source_sha=source_sha, tooling_sha=tooling_sha)
    producer = resolve_trusted_candidate_producer("ms-manager-app")
    if isinstance(producer, Err):
        return producer

    with TemporaryDirectory(prefix="app-candidate-probe-") as tmp:
        metadata_dir = Path(tmp) / "metadata"
        downloaded = download_release_assets(
            workspace_root=workspace_root,
            repo=config.APP_REPO_SLUG,
            tag=candidate_tag,
            out_dir=metadata_dir,
            patterns=("candidate.json", "checksums.txt", "candidate.json.sig"),
        )
        if isinstance(downloaded, Err):
            if downloaded.error.kind == "artifact_missing":
                exists = release_exists_by_tag(
                    workspace_root=workspace_root,
                    repo=config.APP_REPO_SLUG,
                    tag=candidate_tag,
                )
                if isinstance(exists, Err):
                    return exists
                if exists.value:
                    return Ok(AppCandidateState.INCOMPLETE)
                return Ok(AppCandidateState.MISSING)
            return downloaded

        if not _candidate_metadata_complete(metadata_dir):
            return Ok(AppCandidateState.INCOMPLETE)

        inspected = inspect_candidate_metadata(
            workspace_root=workspace_root,
            request=CandidateVerifyRequest(
                artifacts_dir=metadata_dir,
                manifest_path=metadata_dir / "candidate.json",
                checksums_path=metadata_dir / "checksums.txt",
                sig_path=metadata_dir / "candidate.json.sig",
                expected_producer_repo=producer.value.producer_repo,
                expected_producer_kind=producer.value.producer_kind,
                expected_workflow_file=producer.value.workflow_file,
                expected_input_repos=app_candidate_input_repos(
                    source_sha=source_sha,
                    tooling_sha=tooling_sha,
                ),
                public_key_b64=producer.value.public_key_b64,
            ),
        )
        if isinstance(inspected, Err):
            return Err(
                ReleaseError(
                    kind=inspected.error.kind,
                    message=f"candidate invalid: {candidate_tag}",
                    hint=inspected.error.pretty(),
                )
            )

        return Ok(AppCandidateState.READY)


def _wait_for_app_candidate_ready(
    *,
    workspace_root: Path,
    source_sha: str,
    tooling_sha: str,
) -> Result[AppCandidateState, ReleaseError]:
    state = _probe_app_candidate(
        workspace_root=workspace_root,
        source_sha=source_sha,
        tooling_sha=tooling_sha,
    )
    if isinstance(state, Err):
        return state
    if state.value is not AppCandidateState.INCOMPLETE:
        return state

    for _ in range(_INCOMPLETE_PROBE_ATTEMPTS - 1):
        sleep(_INCOMPLETE_PROBE_DELAY_SECONDS)
        state = _probe_app_candidate(
            workspace_root=workspace_root,
            source_sha=source_sha,
            tooling_sha=tooling_sha,
        )
        if isinstance(state, Err):
            return state
        if state.value is not AppCandidateState.INCOMPLETE:
            return state

    return state


def app_candidate_tag(*, source_sha: str, tooling_sha: str) -> str:
    return f"rc-{source_sha}-tooling-{tooling_sha}"


def candidate_release_url(*, candidate_tag: str) -> str:
    return f"https://github.com/{config.APP_REPO_SLUG}/releases/tag/{candidate_tag}"


def app_candidate_input_repos(
    *,
    source_sha: str,
    tooling_sha: str,
) -> tuple[CandidateInputRepo, ...]:
    return (
        CandidateInputRepo(id="ms-manager", repo=config.APP_REPO_SLUG, sha=source_sha),
        CandidateInputRepo(
            id="ms-dev-env",
            repo="petitechose-midi-studio/ms-dev-env",
            sha=tooling_sha,
        ),
    )


def _candidate_metadata_complete(metadata_dir: Path) -> bool:
    required = (
        metadata_dir / "candidate.json",
        metadata_dir / "checksums.txt",
        metadata_dir / "candidate.json.sig",
    )
    return all(path.is_file() for path in required)
