from __future__ import annotations

from dataclasses import dataclass

from ms.core.result import Err, Ok, Result
from ms.release.errors import ReleaseError


@dataclass(frozen=True, slots=True)
class TrustedCandidateProducer:
    id: str
    candidate_repo: str
    producer_repo: str
    producer_kind: str
    workflow_file: str
    public_key_b64: str


TRUSTED_CANDIDATE_PRODUCERS: tuple[TrustedCandidateProducer, ...] = (
    TrustedCandidateProducer(
        id="loader-binaries",
        candidate_repo="petitechose-midi-studio/loader",
        producer_repo="petitechose-midi-studio/loader",
        producer_kind="loader-binaries",
        workflow_file=".github/workflows/candidate.yml",
        public_key_b64="4aCCjNy9oSR1bQmO+JCE2r/r8R0nC9jBmOHVrKVc+Y4=",
    ),
    TrustedCandidateProducer(
        id="oc-bridge-binaries",
        candidate_repo="open-control/bridge",
        producer_repo="open-control/bridge",
        producer_kind="oc-bridge-binaries",
        workflow_file=".github/workflows/candidate.yml",
        public_key_b64="DPD0tiPoOR/oCZmhXBqDwPQWL7DSr8Fffp1q+Mmfgdk=",
    ),
    TrustedCandidateProducer(
        id="core-default-firmware",
        candidate_repo="petitechose-midi-studio/core",
        producer_repo="petitechose-midi-studio/core",
        producer_kind="core-default-firmware",
        workflow_file=".github/workflows/candidate.yml",
        public_key_b64="SAmvKafqhAmX4/3qSW+Lz5eo3XpF0WKeh5HntqL/CSA=",
    ),
    TrustedCandidateProducer(
        id="plugin-bitwig-extension",
        candidate_repo="petitechose-midi-studio/plugin-bitwig",
        producer_repo="petitechose-midi-studio/plugin-bitwig",
        producer_kind="plugin-bitwig-extension",
        workflow_file=".github/workflows/candidate-extension.yml",
        public_key_b64="6ImRpNtLGhjUIEjc3Mh+ql/mO9jnfxamUZUxeXsfEZM=",
    ),
    TrustedCandidateProducer(
        id="plugin-bitwig-firmware",
        candidate_repo="petitechose-midi-studio/plugin-bitwig",
        producer_repo="petitechose-midi-studio/plugin-bitwig",
        producer_kind="plugin-bitwig-firmware",
        workflow_file=".github/workflows/candidate-firmware.yml",
        public_key_b64="6ImRpNtLGhjUIEjc3Mh+ql/mO9jnfxamUZUxeXsfEZM=",
    ),
    TrustedCandidateProducer(
        id="ms-manager-app",
        candidate_repo="petitechose-midi-studio/ms-manager",
        producer_repo="petitechose-midi-studio/ms-manager",
        producer_kind="ms-manager-app",
        workflow_file=".github/workflows/candidate.yml",
        public_key_b64="Rj+AQxyDbizwMO663nl0bpWzv6IY9rdMuREUqsI91Qo=",
    ),
)

_TRUSTED_CANDIDATE_PRODUCERS_BY_ID = {
    producer.id: producer for producer in TRUSTED_CANDIDATE_PRODUCERS
}


def resolve_trusted_candidate_producer(
    producer_id: str,
) -> Result[TrustedCandidateProducer, ReleaseError]:
    producer = _TRUSTED_CANDIDATE_PRODUCERS_BY_ID.get(producer_id)
    if producer is None:
        return Err(
            ReleaseError(
                kind="invalid_input",
                message=f"unknown candidate producer: {producer_id}",
                hint="Check the trusted candidate producer mapping in ms-dev-env.",
            )
        )
    return Ok(producer)

