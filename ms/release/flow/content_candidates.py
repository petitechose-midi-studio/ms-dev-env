from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory

from ms.core.result import Err, Ok, Result
from ms.output.console import ConsoleProtocol, Style
from ms.release.domain import CandidateInputRepo, resolve_trusted_candidate_producer
from ms.release.domain.models import PinnedRepo
from ms.release.errors import ReleaseError
from ms.release.flow.candidate_workflow import CandidateVerifyRequest, inspect_candidate_bundle
from ms.release.infra.github import get_repo_file_text
from ms.release.infra.github.releases import download_release_assets
from ms.release.infra.github.run_watch import watch_run
from ms.release.infra.github.workflows import WorkflowRun, dispatch_candidate_workflow

_UI_DEP_RE = re.compile(
    r"(?m)^\s*ms-ui=https://github\.com/petitechose-midi-studio/ui\.git#([0-9a-f]{40})\s*$"
)


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


def ensure_content_candidates(
    *,
    workspace_root: Path,
    console: ConsoleProtocol,
    pinned: tuple[PinnedRepo, ...],
    dry_run: bool,
) -> Result[tuple[EnsuredContentCandidate, ...], ReleaseError]:
    planned = plan_content_candidates(workspace_root=workspace_root, pinned=pinned)
    if isinstance(planned, Err):
        return planned

    ensured: list[EnsuredContentCandidate] = []
    for target in planned.value:
        ready = _probe_content_candidate(
            workspace_root=workspace_root,
            target=target,
        )
        if isinstance(ready, Err):
            return ready
        if ready.value:
            console.print(f"candidate ready: {target.label}", Style.DIM)
            ensured.append(EnsuredContentCandidate(target=target, ready_on_entry=True, run=None))
            continue

        console.print(f"candidate build required: {target.label}", Style.DIM)
        dispatched = dispatch_candidate_workflow(
            workspace_root=workspace_root,
            repo_slug=target.repo_slug,
            workflow_file=target.workflow_file,
            ref=target.ref,
            inputs=target.workflow_inputs,
            console=console,
            dry_run=dry_run,
        )
        if isinstance(dispatched, Err):
            return dispatched

        watched = watch_run(
            workspace_root=workspace_root,
            run_id=dispatched.value.id,
            repo_slug=target.repo_slug,
            console=console,
            dry_run=dry_run,
        )
        if isinstance(watched, Err):
            return watched

        if not dry_run:
            confirmed = _probe_content_candidate(
                workspace_root=workspace_root,
                target=target,
            )
            if isinstance(confirmed, Err):
                return confirmed
            if not confirmed.value:
                return Err(
                    ReleaseError(
                        kind="workflow_failed",
                        message=(
                            "candidate still unavailable after successful workflow: "
                            f"{target.label}"
                        ),
                        hint=target.candidate_tag,
                    )
                )

        ensured.append(
            EnsuredContentCandidate(
                target=target,
                ready_on_entry=False,
                run=dispatched.value,
            )
        )

    return Ok(tuple(ensured))


def plan_content_candidates(
    *,
    workspace_root: Path,
    pinned: tuple[PinnedRepo, ...],
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
    ui_sha = _resolve_core_ui_sha(workspace_root=workspace_root, core_pin=core_pin)
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

    return Ok(
        (
            ContentCandidateTarget(
                id="loader-binaries",
                label=f"loader {loader_pin.sha[:12]}",
                producer_id="loader-binaries",
                repo_slug=loader_pin.repo.slug,
                workflow_file=".github/workflows/candidate.yml",
                ref=loader_pin.repo.ref,
                candidate_tag=f"rc-{loader_pin.sha}",
                workflow_inputs=(("source_sha", loader_pin.sha),),
                expected_input_repos=(
                    CandidateInputRepo(
                        id="loader",
                        repo=loader_pin.repo.slug,
                        sha=loader_pin.sha,
                    ),
                ),
                public_key_b64=producer_keys.value["loader-binaries"],
            ),
            ContentCandidateTarget(
                id="oc-bridge-binaries",
                label=f"oc-bridge {bridge_pin.sha[:12]}",
                producer_id="oc-bridge-binaries",
                repo_slug=bridge_pin.repo.slug,
                workflow_file=".github/workflows/candidate.yml",
                ref=bridge_pin.repo.ref,
                candidate_tag=f"rc-{bridge_pin.sha}",
                workflow_inputs=(("source_sha", bridge_pin.sha),),
                expected_input_repos=(
                    CandidateInputRepo(
                        id="oc-bridge",
                        repo=bridge_pin.repo.slug,
                        sha=bridge_pin.sha,
                    ),
                ),
                public_key_b64=producer_keys.value["oc-bridge-binaries"],
            ),
            ContentCandidateTarget(
                id="core-default-firmware",
                label=f"core firmware {core_pin.sha[:12]}",
                producer_id="core-default-firmware",
                repo_slug=core_pin.repo.slug,
                workflow_file=".github/workflows/candidate.yml",
                ref=core_pin.repo.ref,
                candidate_tag=f"rc-{core_pin.sha}",
                workflow_inputs=(("source_sha", core_pin.sha),),
                expected_input_repos=(
                    CandidateInputRepo(
                        id="core",
                        repo=core_pin.repo.slug,
                        sha=core_pin.sha,
                    ),
                ),
                public_key_b64=producer_keys.value["core-default-firmware"],
            ),
            ContentCandidateTarget(
                id="plugin-bitwig-extension",
                label=f"bitwig extension {bitwig_pin.sha[:12]}",
                producer_id="plugin-bitwig-extension",
                repo_slug=bitwig_pin.repo.slug,
                workflow_file=".github/workflows/candidate-extension.yml",
                ref=bitwig_pin.repo.ref,
                candidate_tag=f"rc-plugin-bitwig-extension-{bitwig_pin.sha}",
                workflow_inputs=(("source_sha", bitwig_pin.sha),),
                expected_input_repos=(
                    CandidateInputRepo(
                        id="plugin-bitwig",
                        repo=bitwig_pin.repo.slug,
                        sha=bitwig_pin.sha,
                    ),
                ),
                public_key_b64=producer_keys.value["plugin-bitwig-extension"],
            ),
            ContentCandidateTarget(
                id="plugin-bitwig-firmware",
                label=f"bitwig firmware {core_pin.sha[:12]} + {bitwig_pin.sha[:12]}",
                producer_id="plugin-bitwig-firmware",
                repo_slug=bitwig_pin.repo.slug,
                workflow_file=".github/workflows/candidate-firmware.yml",
                ref=bitwig_pin.repo.ref,
                candidate_tag=f"rc-plugin-bitwig-firmware-{core_pin.sha}-{bitwig_pin.sha}",
                workflow_inputs=(("source_sha", bitwig_pin.sha), ("core_sha", core_pin.sha)),
                expected_input_repos=(
                    CandidateInputRepo(
                        id="plugin-bitwig",
                        repo=bitwig_pin.repo.slug,
                        sha=bitwig_pin.sha,
                    ),
                    CandidateInputRepo(
                        id="core",
                        repo=core_pin.repo.slug,
                        sha=core_pin.sha,
                    ),
                    CandidateInputRepo(
                        id="ui",
                        repo="petitechose-midi-studio/ui",
                        sha=ui_sha.value,
                    ),
                ),
                public_key_b64=producer_keys.value["plugin-bitwig-firmware"],
            ),
        )
    )


def _probe_content_candidate(
    *,
    workspace_root: Path,
    target: ContentCandidateTarget,
) -> Result[bool, ReleaseError]:
    with TemporaryDirectory(prefix="candidate-probe-") as tmp:
        metadata_dir = Path(tmp) / "metadata"
        downloaded = download_release_assets(
            workspace_root=workspace_root,
            repo=target.repo_slug,
            tag=target.candidate_tag,
            out_dir=metadata_dir,
            patterns=("candidate.json", "candidate.json.sig"),
        )
        if isinstance(downloaded, Err):
            if downloaded.error.kind == "artifact_missing":
                return Ok(False)
            return downloaded

        inspected = inspect_candidate_bundle(
            workspace_root=workspace_root,
            request=CandidateVerifyRequest(
                artifacts_dir=metadata_dir,
                manifest_path=metadata_dir / "candidate.json",
                checksums_path=metadata_dir / "checksums.txt",
                sig_path=metadata_dir / "candidate.json.sig",
                expected_input_repos=target.expected_input_repos,
                public_key_b64=target.public_key_b64,
            ),
        )
        if isinstance(inspected, Err):
            if inspected.error.kind in {"invalid_input", "verification_failed"}:
                return Ok(False)
            return inspected
        return Ok(True)


def _resolve_core_ui_sha(
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
