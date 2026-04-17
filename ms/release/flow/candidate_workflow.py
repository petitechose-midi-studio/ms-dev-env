from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from ms.core.result import Err, Ok, Result
from ms.release.domain import (
    CANDIDATE_SCHEMA,
    CandidateArtifact,
    CandidateInputRepo,
    CandidateManifest,
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

from . import candidate_inputs as _candidate_inputs
from .candidate_types import CandidateArtifactSpec, CandidateVerifyRequest, CandidateWriteRequest

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
    manifest = load_candidate_manifest(request.manifest_path)
    if isinstance(manifest, Err):
        return manifest
    verified = verify_candidate_manifest(
        workspace_root=workspace_root,
        manifest_path=request.manifest_path,
        sig_path=request.sig_path,
        pk_env=request.public_key_env,
    )
    if isinstance(verified, Err):
        return verified
    payload = validate_candidate_payload(
        artifacts_dir=request.artifacts_dir,
        manifest=manifest.value,
        checksums_path=request.checksums_path,
    )
    if isinstance(payload, Err):
        return payload
    expectations = _validate_candidate_expectations(request=request, manifest=manifest.value)
    if isinstance(expectations, Err):
        return expectations
    return manifest


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


def _default_generated_at() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
