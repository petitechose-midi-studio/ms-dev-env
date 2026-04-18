from __future__ import annotations

from ms.release.domain import CandidateInputRepo

from . import candidate_inputs as _candidate_inputs
from .candidate_fetch import fetch_candidate_assets
from .candidate_types import (
    CandidateArtifactSpec,
    CandidateFetchRequest,
    CandidateFetchResult,
    CandidateVerifyRequest,
    CandidateWriteRequest,
)
from .candidate_verify import inspect_candidate_bundle, verify_candidate_bundle
from .candidate_write import write_candidate_bundle

load_candidate_artifact_specs = _candidate_inputs.load_candidate_artifact_specs
load_candidate_input_repos = _candidate_inputs.load_candidate_input_repos
load_string_pairs_json = _candidate_inputs.load_string_pairs_json

__all__ = [
    "CandidateArtifactSpec",
    "CandidateFetchRequest",
    "CandidateFetchResult",
    "CandidateInputRepo",
    "CandidateVerifyRequest",
    "CandidateWriteRequest",
    "fetch_candidate_assets",
    "inspect_candidate_bundle",
    "load_candidate_artifact_specs",
    "load_candidate_input_repos",
    "load_string_pairs_json",
    "verify_candidate_bundle",
    "write_candidate_bundle",
]
