from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

from ms.core.result import Err, Ok, Result
from ms.output.console import ConsoleProtocol, Style
from ms.release.domain.models import ReleasePlan
from ms.release.errors import ReleaseError
from ms.release.flow.candidate_types import CandidateVerifyRequest
from ms.release.flow.candidate_verify import inspect_candidate_metadata
from ms.release.infra.github.releases import download_release_assets
from ms.release.infra.github.run_watch import watch_run
from ms.release.infra.github.workflows import dispatch_candidate_workflow

from .content_candidate_planning import plan_content_candidates
from .content_candidate_types import ContentCandidateTarget, EnsuredContentCandidate


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
        if ready.value:
            console.print(f"candidate ready: {target.label}", Style.DIM)
            ensured.append(EnsuredContentCandidate(target=target, ready_on_entry=True, run=None))
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
            if not confirmed.value:
                return Err(
                    ReleaseError(
                        kind="workflow_failed",
                        message=(
                            "candidate still unavailable after successful workflow: "
                            f"{target.label}"
                        ),
                        hint=target.candidate_tag,
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
) -> Result[bool, ReleaseError]:
    with TemporaryDirectory(prefix="candidate-probe-") as tmp:
        metadata_dir = Path(tmp) / "metadata"
        downloaded = download_release_assets(
            workspace_root=workspace_root,
            repo=target.repo_slug,
            tag=target.candidate_tag,
            out_dir=metadata_dir,
            patterns=("candidate.json", "candidate.json.sig"),
        )
        if isinstance(downloaded, Err):
            if downloaded.error.kind == "artifact_missing":
                return Ok(False)
            return downloaded

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
            if inspected.error.kind in {"invalid_input", "verification_failed"}:
                return Ok(False)
            return inspected
        return Ok(True)
