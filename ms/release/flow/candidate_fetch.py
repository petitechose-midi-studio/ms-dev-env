from __future__ import annotations

from pathlib import Path
from shutil import copy2
from tempfile import TemporaryDirectory

from ms.core.result import Err, Ok, Result
from ms.release.domain import CandidateManifest, resolve_trusted_candidate_producer
from ms.release.errors import ReleaseError
from ms.release.infra.github.releases import download_release_assets

from .candidate_types import CandidateFetchRequest, CandidateFetchResult, CandidateVerifyRequest
from .candidate_verify import verify_candidate_bundle


def fetch_candidate_assets(
    *,
    workspace_root: Path,
    request: CandidateFetchRequest,
) -> Result[CandidateFetchResult, ReleaseError]:
    if not request.asset_filenames:
        return Err(
            ReleaseError(
                kind="invalid_input",
                message="candidate fetch requires at least one asset filename",
            )
        )

    producer = resolve_trusted_candidate_producer(request.producer_id)
    if isinstance(producer, Err):
        return producer

    with TemporaryDirectory(prefix="candidate-fetch-") as tmp:
        artifacts_dir = Path(tmp) / "artifacts"
        downloaded = download_release_assets(
            workspace_root=workspace_root,
            repo=producer.value.candidate_repo,
            tag=request.candidate_tag,
            out_dir=artifacts_dir,
        )
        if isinstance(downloaded, Err):
            return downloaded

        verified = verify_candidate_bundle(
            workspace_root=workspace_root,
            request=CandidateVerifyRequest(
                artifacts_dir=artifacts_dir,
                manifest_path=artifacts_dir / "candidate.json",
                checksums_path=artifacts_dir / "checksums.txt",
                sig_path=artifacts_dir / "candidate.json.sig",
                expected_producer_repo=producer.value.producer_repo,
                expected_producer_kind=producer.value.producer_kind,
                expected_workflow_file=producer.value.workflow_file,
                expected_input_repos=request.expected_input_repos,
                public_key_b64=producer.value.public_key_b64,
            ),
        )
        if isinstance(verified, Err):
            return verified

        copied = _copy_requested_candidate_assets(
            artifacts_dir=artifacts_dir,
            output_dir=request.output_dir,
            filenames=request.asset_filenames,
            manifest=verified.value,
        )
        if isinstance(copied, Err):
            return copied

        return Ok(
            CandidateFetchResult(
                producer_id=request.producer_id,
                candidate_repo=producer.value.candidate_repo,
                candidate_tag=request.candidate_tag,
                output_dir=request.output_dir,
                copied_files=copied.value,
                manifest=verified.value,
            )
        )


def _copy_requested_candidate_assets(
    *,
    artifacts_dir: Path,
    output_dir: Path,
    filenames: tuple[str, ...],
    manifest: CandidateManifest,
) -> Result[tuple[Path, ...], ReleaseError]:
    available = {artifact.filename for artifact in manifest.artifacts}
    unknown = [filename for filename in filenames if filename not in available]
    if unknown:
        return Err(
            ReleaseError(
                kind="invalid_input",
                message="candidate does not expose requested asset filenames",
                hint=", ".join(sorted(unknown)),
            )
        )

    output_dir.mkdir(parents=True, exist_ok=True)
    copied: list[Path] = []
    for filename in filenames:
        source = artifacts_dir / filename
        if not source.exists():
            return Err(
                ReleaseError(
                    kind="artifact_missing",
                    message=f"candidate asset missing after verification: {filename}",
                )
            )
        destination = output_dir / filename
        copy2(source, destination)
        copied.append(destination)
    return Ok(tuple(copied))
