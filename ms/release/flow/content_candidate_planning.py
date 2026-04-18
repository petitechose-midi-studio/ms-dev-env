from __future__ import annotations

import re
from pathlib import Path

from ms.core.result import Err, Ok, Result
from ms.release.domain import CandidateInputRepo, resolve_trusted_candidate_producer
from ms.release.domain.models import PinnedRepo, ReleaseTooling
from ms.release.errors import ReleaseError
from ms.release.infra.github import get_repo_file_text

from .content_candidate_types import ContentCandidateTarget
from .release_tooling import tooling_input_repo

_UI_DEP_RE = re.compile(
    r"(?m)^\s*ms-ui=https://github\.com/petitechose-midi-studio/ui\.git#([0-9a-f]{40})\s*$"
)


def plan_content_candidates(
    *,
    workspace_root: Path,
    pinned: tuple[PinnedRepo, ...],
    tooling: ReleaseTooling,
) -> Result[tuple[ContentCandidateTarget, ...], ReleaseError]:
    pinned_by_id = {pin.repo.id: pin for pin in pinned}
    missing = [
        repo_id
        for repo_id in ("loader", "oc-bridge", "core", "plugin-bitwig")
        if repo_id not in pinned_by_id
    ]
    if missing:
        return Err(
            ReleaseError(
                kind="invalid_input",
                message="content release is missing pinned repos required for candidates",
                hint=", ".join(sorted(missing)),
            )
        )

    core_pin = pinned_by_id["core"]
    ui_sha = resolve_core_ui_sha(workspace_root=workspace_root, core_pin=core_pin)
    if isinstance(ui_sha, Err):
        return ui_sha

    loader_pin = pinned_by_id["loader"]
    bridge_pin = pinned_by_id["oc-bridge"]
    bitwig_pin = pinned_by_id["plugin-bitwig"]
    producer_keys = _resolve_candidate_public_keys(
        (
            "loader-binaries",
            "oc-bridge-binaries",
            "core-default-firmware",
            "plugin-bitwig-extension",
            "plugin-bitwig-firmware",
        )
    )
    if isinstance(producer_keys, Err):
        return producer_keys

    targets = (
        _single_repo_candidate_target(
            target_id="loader-binaries",
            label=f"loader {loader_pin.sha[:12]}",
            producer_id="loader-binaries",
            repo_slug=loader_pin.repo.slug,
            workflow_file=".github/workflows/candidate.yml",
            ref=loader_pin.repo.ref,
            candidate_tag=f"rc-{loader_pin.sha}-tooling-{tooling.sha}",
            input_repo_id="loader",
            source_sha=loader_pin.sha,
            tooling=tooling,
            public_key_b64=producer_keys.value["loader-binaries"],
        ),
        _single_repo_candidate_target(
            target_id="oc-bridge-binaries",
            label=f"oc-bridge {bridge_pin.sha[:12]}",
            producer_id="oc-bridge-binaries",
            repo_slug=bridge_pin.repo.slug,
            workflow_file=".github/workflows/candidate.yml",
            ref=bridge_pin.repo.ref,
            candidate_tag=f"rc-{bridge_pin.sha}-tooling-{tooling.sha}",
            input_repo_id="oc-bridge",
            source_sha=bridge_pin.sha,
            tooling=tooling,
            public_key_b64=producer_keys.value["oc-bridge-binaries"],
        ),
        _single_repo_candidate_target(
            target_id="core-default-firmware",
            label=f"core firmware {core_pin.sha[:12]}",
            producer_id="core-default-firmware",
            repo_slug=core_pin.repo.slug,
            workflow_file=".github/workflows/candidate.yml",
            ref=core_pin.repo.ref,
            candidate_tag=f"rc-{core_pin.sha}-tooling-{tooling.sha}",
            input_repo_id="core",
            source_sha=core_pin.sha,
            tooling=tooling,
            public_key_b64=producer_keys.value["core-default-firmware"],
        ),
        _single_repo_candidate_target(
            target_id="plugin-bitwig-extension",
            label=f"bitwig extension {bitwig_pin.sha[:12]}",
            producer_id="plugin-bitwig-extension",
            repo_slug=bitwig_pin.repo.slug,
            workflow_file=".github/workflows/candidate-extension.yml",
            ref=bitwig_pin.repo.ref,
            candidate_tag=f"rc-plugin-bitwig-extension-{bitwig_pin.sha}-tooling-{tooling.sha}",
            input_repo_id="plugin-bitwig",
            source_sha=bitwig_pin.sha,
            tooling=tooling,
            public_key_b64=producer_keys.value["plugin-bitwig-extension"],
        ),
        _plugin_bitwig_firmware_target(
            bitwig_pin=bitwig_pin,
            core_pin=core_pin,
            ui_sha=ui_sha.value,
            tooling=tooling,
            public_key_b64=producer_keys.value["plugin-bitwig-firmware"],
        ),
    )
    return Ok(
        targets
    )


def resolve_core_ui_sha(
    *,
    workspace_root: Path,
    core_pin: PinnedRepo,
) -> Result[str, ReleaseError]:
    text = get_repo_file_text(
        workspace_root=workspace_root,
        repo=core_pin.repo.slug,
        path="platformio.ini",
        ref=core_pin.sha,
    )
    if isinstance(text, Err):
        return text

    match = _UI_DEP_RE.search(text.value)
    if match is None:
        return Err(
            ReleaseError(
                kind="invalid_input",
                message="missing pinned ms-ui dependency in core/platformio.ini",
                hint=core_pin.sha,
            )
        )
    return Ok(match.group(1))


def _resolve_candidate_public_keys(
    producer_ids: tuple[str, ...],
) -> Result[dict[str, str], ReleaseError]:
    keys: dict[str, str] = {}
    for producer_id in producer_ids:
        producer = resolve_trusted_candidate_producer(producer_id)
        if isinstance(producer, Err):
            return producer
        keys[producer_id] = producer.value.public_key_b64
    return Ok(keys)


def _single_repo_candidate_target(
    *,
    target_id: str,
    label: str,
    producer_id: str,
    repo_slug: str,
    workflow_file: str,
    ref: str,
    candidate_tag: str,
    input_repo_id: str,
    source_sha: str,
    tooling: ReleaseTooling,
    public_key_b64: str,
) -> ContentCandidateTarget:
    return ContentCandidateTarget(
        id=target_id,
        label=label,
        producer_id=producer_id,
        repo_slug=repo_slug,
        workflow_file=workflow_file,
        ref=ref,
        candidate_tag=candidate_tag,
        workflow_inputs=(("source_sha", source_sha), ("tooling_sha", tooling.sha)),
        expected_input_repos=(
            CandidateInputRepo(id=input_repo_id, repo=repo_slug, sha=source_sha),
            tooling_input_repo(tooling=tooling),
        ),
        public_key_b64=public_key_b64,
    )


def _plugin_bitwig_firmware_target(
    *,
    bitwig_pin: PinnedRepo,
    core_pin: PinnedRepo,
    ui_sha: str,
    tooling: ReleaseTooling,
    public_key_b64: str,
) -> ContentCandidateTarget:
    return ContentCandidateTarget(
        id="plugin-bitwig-firmware",
        label=f"bitwig firmware {core_pin.sha[:12]} + {bitwig_pin.sha[:12]}",
        producer_id="plugin-bitwig-firmware",
        repo_slug=bitwig_pin.repo.slug,
        workflow_file=".github/workflows/candidate-firmware.yml",
        ref=bitwig_pin.repo.ref,
        candidate_tag=(
            f"rc-plugin-bitwig-firmware-{core_pin.sha}-{bitwig_pin.sha}-tooling-{tooling.sha}"
        ),
        workflow_inputs=(
            ("source_sha", bitwig_pin.sha),
            ("core_sha", core_pin.sha),
            ("tooling_sha", tooling.sha),
        ),
        expected_input_repos=(
            CandidateInputRepo(
                id="plugin-bitwig",
                repo=bitwig_pin.repo.slug,
                sha=bitwig_pin.sha,
            ),
            CandidateInputRepo(id="core", repo=core_pin.repo.slug, sha=core_pin.sha),
            CandidateInputRepo(id="ui", repo="petitechose-midi-studio/ui", sha=ui_sha),
            tooling_input_repo(tooling=tooling),
        ),
        public_key_b64=public_key_b64,
    )
