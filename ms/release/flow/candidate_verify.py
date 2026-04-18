from __future__ import annotations

from pathlib import Path

from ms.core.result import Err, Ok, Result
from ms.release.domain import CandidateInputRepo, CandidateManifest
from ms.release.errors import ReleaseError
from ms.release.infra.candidate_contract import load_candidate_manifest, validate_candidate_payload
from ms.release.infra.candidate_signatures import (
    verify_candidate_manifest,
    verify_candidate_manifest_with_public_key,
)

from .candidate_types import CandidateVerifyRequest


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
