from __future__ import annotations

from pathlib import Path

from pytest import MonkeyPatch

from ms.core.result import Err, Ok
from ms.platform.process import ProcessError
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
from ms.release.infra.candidate_signatures import verify_candidate_manifest


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


def test_verify_candidate_manifest_uses_distribution_signature_backend(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    import ms.release.infra.candidate_signatures as signatures

    distribution_root = tmp_path / "distribution"
    distribution_root.mkdir()
    (distribution_root / "Cargo.toml").write_text("[workspace]\n", encoding="utf-8")

    calls: list[tuple[tuple[str, ...], Path]] = []

    def fake_run_process(
        cmd: list[str],
        cwd: Path,
        env: dict[str, str] | None,
        *,
        timeout: float | None,
    ) -> Ok[str]:
        del env, timeout
        calls.append((tuple(cmd), cwd))
        return Ok("")

    monkeypatch.setattr(signatures, "run_process", fake_run_process)

    verified = verify_candidate_manifest(
        workspace_root=tmp_path,
        manifest_path=tmp_path / "candidate.json",
        sig_path=tmp_path / "candidate.json.sig",
    )

    assert isinstance(verified, Ok)
    assert calls == [
        (
            (
                "cargo",
                "run",
                "-p",
                "ms-dist-manifest",
                "--",
                "verify",
                "--in",
                str(tmp_path / "candidate.json"),
                "--sig",
                str(tmp_path / "candidate.json.sig"),
                "--pk-env",
                "MS_CANDIDATE_ED25519_PK",
            ),
            distribution_root,
        )
    ]


def test_derive_candidate_public_key_uses_signature_backend(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    import ms.release.infra.candidate_signatures as signatures

    distribution_root = tmp_path / "distribution"
    distribution_root.mkdir()
    (distribution_root / "Cargo.toml").write_text("[workspace]\n", encoding="utf-8")

    calls: list[tuple[tuple[str, ...], Path]] = []

    def fake_run_process(
        cmd: list[str],
        cwd: Path,
        env: dict[str, str] | None,
        *,
        timeout: float | None,
    ) -> Ok[str]:
        del env, timeout
        calls.append((tuple(cmd), cwd))
        return Ok("pubkey\n")

    monkeypatch.setattr(signatures, "run_process", fake_run_process)

    derived = signatures.derive_candidate_public_key(workspace_root=tmp_path)

    assert isinstance(derived, Ok)
    assert derived.value == "pubkey"
    assert calls == [
        (
            (
                "cargo",
                "run",
                "-p",
                "ms-dist-manifest",
                "--",
                "pubkey",
                "--key-env",
                "MS_CANDIDATE_ED25519_SK",
            ),
            distribution_root,
        )
    ]


def test_verify_candidate_manifest_reports_backend_failure(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    import ms.release.infra.candidate_signatures as signatures

    distribution_root = tmp_path / "distribution"
    distribution_root.mkdir()
    (distribution_root / "Cargo.toml").write_text("[workspace]\n", encoding="utf-8")

    def fake_run_process(
        cmd: list[str],
        cwd: Path,
        env: dict[str, str] | None,
        *,
        timeout: float | None,
    ) -> Err[ProcessError]:
        del cmd, cwd, env, timeout
        return Err(
            ProcessError(
                command=("cargo",),
                returncode=1,
                stdout="",
                stderr="verify failed",
            )
        )

    monkeypatch.setattr(signatures, "run_process", fake_run_process)

    verified = verify_candidate_manifest(
        workspace_root=tmp_path,
        manifest_path=tmp_path / "candidate.json",
        sig_path=tmp_path / "candidate.json.sig",
    )

    assert isinstance(verified, Err)
    assert verified.error.kind == "verification_failed"
    assert verified.error.message == "candidate signature command failed"
