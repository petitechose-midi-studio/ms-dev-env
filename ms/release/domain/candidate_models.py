from __future__ import annotations

from dataclasses import dataclass

CANDIDATE_SCHEMA = "ms-candidate/v1"


@dataclass(frozen=True, slots=True)
class CandidateInputRepo:
    id: str
    repo: str
    sha: str


@dataclass(frozen=True, slots=True)
class CandidateArtifact:
    id: str
    filename: str
    kind: str
    os: str | None
    arch: str | None
    size: int
    sha256: str


@dataclass(frozen=True, slots=True)
class CandidateManifest:
    schema: str
    producer_repo: str
    producer_kind: str
    workflow_file: str
    run_id: int
    run_attempt: int
    generated_at: str
    build_input_fingerprint: str
    recipe_fingerprint: str
    input_repos: tuple[CandidateInputRepo, ...]
    toolchain: tuple[tuple[str, str], ...]
    config: tuple[tuple[str, str], ...]
    artifacts: tuple[CandidateArtifact, ...]

    def repos_by_id(self) -> dict[str, CandidateInputRepo]:
        return {repo.id: repo for repo in self.input_repos}
