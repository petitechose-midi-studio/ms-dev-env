from __future__ import annotations

import base64
from pathlib import Path

from pytest import MonkeyPatch

from ms.core.result import Err, Ok
from ms.release.domain import CANDIDATE_SCHEMA, CandidateInputRepo, CandidateManifest
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


def test_compute_build_input_fingerprint_is_order_independent() -> None:
    repos_a = (
        CandidateInputRepo(
            id="plugin-bitwig",
            repo="petitechose-midi-studio/plugin-bitwig",
            sha="b" * 40,
        ),
        CandidateInputRepo(id="core", repo="petitechose-midi-studio/core", sha="a" * 40),
    )
    repos_b = (repos_a[1], repos_a[0])

    left = compute_build_input_fingerprint(
        producer_kind="bitwig-firmware",
        input_repos=repos_a,
        recipe_fingerprint="r" * 64,
        toolchain=(("platformio", "6.1.18"),),
        config=(("ui_sha", "c" * 40),),
    )
    right = compute_build_input_fingerprint(
        producer_kind="bitwig-firmware",
        input_repos=repos_b,
        recipe_fingerprint="r" * 64,
        toolchain=(("platformio", "6.1.18"),),
        config=(("ui_sha", "c" * 40),),
    )

    assert left == right


def test_compute_recipe_fingerprint_changes_when_inputs_change(tmp_path: Path) -> None:
    (tmp_path / "a.txt").write_text("one\n", encoding="utf-8")
    (tmp_path / "b.txt").write_text("two\n", encoding="utf-8")

    first = compute_recipe_fingerprint(base_dir=tmp_path, relative_paths=("a.txt", "b.txt"))
    assert isinstance(first, Ok)

    (tmp_path / "b.txt").write_text("three\n", encoding="utf-8")

    second = compute_recipe_fingerprint(base_dir=tmp_path, relative_paths=("a.txt", "b.txt"))
    assert isinstance(second, Ok)
    assert first.value != second.value


def test_candidate_manifest_roundtrip_and_payload_validation(tmp_path: Path) -> None:
    artifacts_dir = tmp_path / "artifacts"
    artifacts_dir.mkdir()
    payload = artifacts_dir / "firmware.hex"
    payload.write_bytes(b"hex payload")

    artifact = describe_candidate_artifact(
        path=payload,
        artifact_id="firmware-default",
        kind="firmware",
        arch="teensy4.1",
    )
    assert isinstance(artifact, Ok)

    manifest = CandidateManifest(
        schema=CANDIDATE_SCHEMA,
        producer_repo="petitechose-midi-studio/core",
        producer_kind="core-default-firmware",
        workflow_file=".github/workflows/candidate.yml",
        run_id=123,
        run_attempt=1,
        generated_at="2026-04-17T21:00:00Z",
        build_input_fingerprint="f" * 64,
        recipe_fingerprint="r" * 64,
        input_repos=(
            CandidateInputRepo(
                id="core",
                repo="petitechose-midi-studio/core",
                sha="a" * 40,
            ),
        ),
        toolchain=(("platformio", "6.1.18"),),
        config=(("platformio_ini_sha256", "b" * 64),),
        artifacts=(artifact.value,),
    )

    manifest_path = tmp_path / "candidate.json"
    checksums_path = tmp_path / "checksums.txt"

    written = write_candidate_manifest(path=manifest_path, manifest=manifest)
    assert isinstance(written, Ok)
    checksums_written = write_candidate_checksums(path=checksums_path, manifest=manifest)
    assert isinstance(checksums_written, Ok)

    loaded = load_candidate_manifest(manifest_path)
    assert isinstance(loaded, Ok)
    assert loaded.value == manifest

    validated = validate_candidate_payload(
        artifacts_dir=artifacts_dir,
        manifest=loaded.value,
        checksums_path=checksums_path,
    )
    assert isinstance(validated, Ok)


def test_candidate_signatures_roundtrip_without_distribution_repo(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    manifest_path = tmp_path / "candidate.json"
    sig_path = tmp_path / "candidate.json.sig"
    manifest_path.write_text('{"schema":"ms-candidate/v1"}\n', encoding="utf-8")

    seed = bytes(range(32))
    seed_b64 = base64.b64encode(seed).decode("ascii")
    monkeypatch.setenv("MS_CANDIDATE_ED25519_SK", seed_b64)

    signed = sign_candidate_manifest(
        workspace_root=tmp_path,
        manifest_path=manifest_path,
        sig_path=sig_path,
    )
    assert isinstance(signed, Ok)

    derived = derive_candidate_public_key(workspace_root=tmp_path)
    assert isinstance(derived, Ok)
    monkeypatch.setenv("MS_CANDIDATE_ED25519_PK", derived.value)

    verified = verify_candidate_manifest(
        workspace_root=tmp_path,
        manifest_path=manifest_path,
        sig_path=sig_path,
    )
    assert isinstance(verified, Ok)

    verified_with_explicit_key = verify_candidate_manifest_with_public_key(
        workspace_root=tmp_path,
        manifest_path=manifest_path,
        sig_path=sig_path,
        public_key_b64=derived.value,
    )
    assert isinstance(verified_with_explicit_key, Ok)


def test_candidate_signatures_report_invalid_signature(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    manifest_path = tmp_path / "candidate.json"
    sig_path = tmp_path / "candidate.json.sig"
    manifest_path.write_text('{"schema":"ms-candidate/v1"}\n', encoding="utf-8")
    sig_path.write_text(base64.b64encode(b"\x00" * 64).decode("ascii"), encoding="utf-8")

    seed = bytes(range(32))
    monkeypatch.setenv("MS_CANDIDATE_ED25519_SK", base64.b64encode(seed).decode("ascii"))
    derived = derive_candidate_public_key(workspace_root=tmp_path)
    assert isinstance(derived, Ok)
    monkeypatch.setenv("MS_CANDIDATE_ED25519_PK", derived.value)

    verified = verify_candidate_manifest(
        workspace_root=tmp_path,
        manifest_path=manifest_path,
        sig_path=sig_path,
    )

    assert isinstance(verified, Err)
    assert verified.error.kind == "verification_failed"
    assert verified.error.message == "candidate signature verify failed"
