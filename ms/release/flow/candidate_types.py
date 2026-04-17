from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ms.release.domain import CandidateInputRepo


@dataclass(frozen=True, slots=True)
class CandidateArtifactSpec:
    id: str
    filename: str
    kind: str
    os: str | None
    arch: str | None


@dataclass(frozen=True, slots=True)
class CandidateWriteRequest:
    artifacts_dir: Path
    manifest_path: Path
    checksums_path: Path
    sig_path: Path
    producer_repo: str
    producer_kind: str
    workflow_file: str
    run_id: int
    run_attempt: int
    input_repos: tuple[CandidateInputRepo, ...]
    artifact_specs: tuple[CandidateArtifactSpec, ...]
    recipe_base_dir: Path
    recipe_paths: tuple[str, ...]
    toolchain: tuple[tuple[str, str], ...]
    config: tuple[tuple[str, str], ...]
    generated_at: str | None = None
    signing_key_env: str = "MS_CANDIDATE_ED25519_SK"


@dataclass(frozen=True, slots=True)
class CandidateVerifyRequest:
    artifacts_dir: Path
    manifest_path: Path
    checksums_path: Path
    sig_path: Path
    expected_producer_repo: str | None = None
    expected_producer_kind: str | None = None
    expected_workflow_file: str | None = None
    expected_input_repos: tuple[CandidateInputRepo, ...] | None = None
    public_key_env: str = "MS_CANDIDATE_ED25519_PK"
