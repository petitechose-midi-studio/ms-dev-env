from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from shutil import copy2
from tempfile import TemporaryDirectory

from ms.core.result import Err, Ok, Result
from ms.release.domain import (
    CANDIDATE_SCHEMA,
    CandidateArtifact,
    CandidateInputRepo,
    CandidateManifest,
    resolve_trusted_candidate_producer,
)
from ms.release.errors import ReleaseError
from ms.release.infra.candidate_contract import (
    compute_build_input_fingerprint,
    compute_recipe_fingerprint,
    describe_candidate_artifact,
    load_candidate_manifest,
    validate_candidate_payload,
    write_candidate_checksums,
    write_candidate_manifest,
)
from ms.release.infra.candidate_signatures import (
    derive_candidate_public_key,
    sign_candidate_manifest,
    verify_candidate_manifest,
    verify_candidate_manifest_with_public_key,
)
from ms.release.infra.github.releases import download_release_assets

from . import candidate_inputs as _candidate_inputs
from .candidate_types import (
    CandidateArtifactSpec,
    CandidateFetchRequest,
    CandidateFetchResult,
    CandidateVerifyRequest,
    CandidateWriteRequest,
)

load_candidate_artifact_specs = _candidate_inputs.load_candidate_artifact_specs
load_candidate_input_repos = _candidate_inputs.load_candidate_input_repos
load_string_pairs_json = _candidate_inputs.load_string_pairs_json


def write_candidate_bundle(
    *,
    workspace_root: Path,
    request: CandidateWriteRequest,
) -> Result[CandidateManifest, ReleaseError]:
    recipe_fingerprint = compute_recipe_fingerprint(
        base_dir=request.recipe_base_dir,
        relative_paths=request.recipe_paths,
    )
    if isinstance(recipe_fingerprint, Err):
        return recipe_fingerprint

    generated_at = request.generated_at or _default_generated_at()
    build_input_fingerprint = compute_build_input_fingerprint(
        producer_kind=request.producer_kind,
        input_repos=request.input_repos,
        recipe_fingerprint=recipe_fingerprint.value,
        toolchain=request.toolchain,
        config=request.config,
    )

    artifacts = _realize_artifacts(
        artifacts_dir=request.artifacts_dir,
        artifact_specs=request.artifact_specs,
    )
    if isinstance(artifacts, Err):
        return artifacts

    manifest = CandidateManifest(
        schema=CANDIDATE_SCHEMA,
        producer_repo=request.producer_repo,
        producer_kind=request.producer_kind,
        workflow_file=request.workflow_file,
        run_id=request.run_id,
        run_attempt=request.run_attempt,
        generated_at=generated_at,
        build_input_fingerprint=build_input_fingerprint,
        recipe_fingerprint=recipe_fingerprint.value,
        input_repos=request.input_repos,
        toolchain=request.toolchain,
        config=request.config,
        artifacts=artifacts.value,
    )

    return _persist_and_verify_candidate(
        workspace_root=workspace_root,
        request=request,
        manifest=manifest,
    )


def verify_candidate_bundle(
    *,
    workspace_root: Path,
    request: CandidateVerifyRequest,
) -> Result[CandidateManifest, ReleaseError]:
    inspected = inspect_candidate_bundle(workspace_root=workspace_root, request=request)
    if isinstance(inspected, Err):
        return inspected
    payload = validate_candidate_payload(
        artifacts_dir=request.artifacts_dir,
        manifest=inspected.value,
        checksums_path=request.checksums_path,
    )
    if isinstance(payload, Err):
        return payload
    return inspected


def inspect_candidate_bundle(
    *,
    workspace_root: Path,
    request: CandidateVerifyRequest,
) -> Result[CandidateManifest, ReleaseError]:
    manifest = load_candidate_manifest(request.manifest_path)
    if isinstance(manifest, Err):
        return manifest
    verified = _verify_candidate_signature(workspace_root=workspace_root, request=request)
    if isinstance(verified, Err):
        return verified
    expectations = _validate_candidate_expectations(request=request, manifest=manifest.value)
    if isinstance(expectations, Err):
        return expectations
    return manifest


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


def _persist_and_verify_candidate(
    *,
    workspace_root: Path,
    request: CandidateWriteRequest,
    manifest: CandidateManifest,
) -> Result[CandidateManifest, ReleaseError]:
    written = write_candidate_manifest(path=request.manifest_path, manifest=manifest)
    if isinstance(written, Err):
        return written
    checksums = write_candidate_checksums(path=request.checksums_path, manifest=manifest)
    if isinstance(checksums, Err):
        return checksums
    signed = sign_candidate_manifest(
        workspace_root=workspace_root,
        manifest_path=request.manifest_path,
        sig_path=request.sig_path,
        key_env=request.signing_key_env,
    )
    if isinstance(signed, Err):
        return signed

    derived_key = derive_candidate_public_key(
        workspace_root=workspace_root,
        key_env=request.signing_key_env,
    )
    if isinstance(derived_key, Err):
        return derived_key
    post_sign_verify = verify_candidate_manifest_with_public_key(
        workspace_root=workspace_root,
        manifest_path=request.manifest_path,
        sig_path=request.sig_path,
        public_key_b64=derived_key.value,
    )
    if isinstance(post_sign_verify, Err):
        return post_sign_verify

    payload = validate_candidate_payload(
        artifacts_dir=request.artifacts_dir,
        manifest=manifest,
        checksums_path=request.checksums_path,
    )
    if isinstance(payload, Err):
        return payload
    return Ok(manifest)


def _realize_artifacts(
    *,
    artifacts_dir: Path,
    artifact_specs: tuple[CandidateArtifactSpec, ...],
) -> Result[tuple[CandidateArtifact, ...], ReleaseError]:
    artifacts: list[CandidateArtifact] = []
    for spec in artifact_specs:
        described = describe_candidate_artifact(
            path=artifacts_dir / spec.filename,
            artifact_id=spec.id,
            kind=spec.kind,
            os_name=spec.os,
            arch=spec.arch,
        )
        if isinstance(described, Err):
            return described
        artifacts.append(described.value)
    return Ok(tuple(artifacts))


def _validate_candidate_expectations(
    *,
    request: CandidateVerifyRequest,
    manifest: CandidateManifest,
) -> Result[None, ReleaseError]:
    if request.expected_producer_repo and manifest.producer_repo != request.expected_producer_repo:
        return Err(
            ReleaseError(
                kind="verification_failed",
                message="candidate producer repo mismatch",
                hint=f"expected {request.expected_producer_repo}, got {manifest.producer_repo}",
            )
        )
    if request.expected_producer_kind and manifest.producer_kind != request.expected_producer_kind:
        return Err(
            ReleaseError(
                kind="verification_failed",
                message="candidate producer kind mismatch",
                hint=f"expected {request.expected_producer_kind}, got {manifest.producer_kind}",
            )
        )
    if request.expected_workflow_file and manifest.workflow_file != request.expected_workflow_file:
        return Err(
            ReleaseError(
                kind="verification_failed",
                message="candidate workflow file mismatch",
                hint=f"expected {request.expected_workflow_file}, got {manifest.workflow_file}",
            )
        )
    if request.expected_input_repos is None:
        return Ok(None)
    return _validate_expected_input_repos(
        expected_input_repos=request.expected_input_repos,
        manifest=manifest,
    )


def _validate_expected_input_repos(
    *,
    expected_input_repos: tuple[CandidateInputRepo, ...],
    manifest: CandidateManifest,
) -> Result[None, ReleaseError]:
    expected = {repo.id: repo for repo in expected_input_repos}
    actual = manifest.repos_by_id()
    if set(expected) != set(actual):
        return Err(
            ReleaseError(
                kind="verification_failed",
                message="candidate input repo set mismatch",
                hint=f"expected {sorted(expected)}, got {sorted(actual)}",
            )
        )
    for repo_id, expected_repo in expected.items():
        actual_repo = actual[repo_id]
        if actual_repo.repo != expected_repo.repo or actual_repo.sha != expected_repo.sha:
            return Err(
                ReleaseError(
                    kind="verification_failed",
                    message=f"candidate input repo mismatch: {repo_id}",
                    hint=(
                        f"expected {expected_repo.repo}@{expected_repo.sha}, "
                        f"got {actual_repo.repo}@{actual_repo.sha}"
                    ),
                )
            )
    return Ok(None)


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


def _default_generated_at() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _verify_candidate_signature(
    *,
    workspace_root: Path,
    request: CandidateVerifyRequest,
) -> Result[None, ReleaseError]:
    if request.public_key_b64 is not None:
        return verify_candidate_manifest_with_public_key(
            workspace_root=workspace_root,
            manifest_path=request.manifest_path,
            sig_path=request.sig_path,
            public_key_b64=request.public_key_b64,
        )
    return verify_candidate_manifest(
        workspace_root=workspace_root,
        manifest_path=request.manifest_path,
        sig_path=request.sig_path,
        pk_env=request.public_key_env,
    )
