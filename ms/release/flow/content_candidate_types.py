from __future__ import annotations

from dataclasses import dataclass

from ms.release.domain import CandidateInputRepo
from ms.release.infra.github.workflows import WorkflowRun


@dataclass(frozen=True, slots=True)
class ContentCandidateTarget:
    id: str
    label: str
    producer_id: str
    repo_slug: str
    workflow_file: str
    ref: str
    candidate_tag: str
    workflow_inputs: tuple[tuple[str, str], ...]
    expected_input_repos: tuple[CandidateInputRepo, ...]
    public_key_b64: str


@dataclass(frozen=True, slots=True)
class EnsuredContentCandidate:
    target: ContentCandidateTarget
    ready_on_entry: bool
    run: WorkflowRun | None


@dataclass(frozen=True, slots=True)
class ContentCandidateAssessment:
    target: ContentCandidateTarget
    available: bool
