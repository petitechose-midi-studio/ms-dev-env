from __future__ import annotations

import base64
import shutil
from pathlib import Path

from pytest import MonkeyPatch

from ms.core.result import Ok
from ms.release.domain import TrustedCandidateProducer
from ms.release.flow.candidate_workflow import (
    CandidateArtifactSpec,
    CandidateFetchRequest,
    CandidateVerifyRequest,
    CandidateWriteRequest,
    fetch_candidate_assets,
    load_candidate_artifact_specs,
    load_candidate_input_repos,
    load_string_pairs_json,
    verify_candidate_bundle,
    write_candidate_bundle,
)


def test_load_candidate_json_inputs(tmp_path: Path) -> None:
    repo_json = (
        '[{"id":"ms-manager","repo":"petitechose-midi-studio/ms-manager","sha":"'
        + ("a" * 40)
        + '"}]'
    )
    (tmp_path / "repos.json").write_text(
        repo_json,
        encoding="utf-8",
    )
    (tmp_path / "artifacts.json").write_text(
        '[{"id":"package-msi","filename":"foo.msi","kind":"package","os":"windows"}]',
        encoding="utf-8",
    )
    (tmp_path / "toolchain.json").write_text('{"node":"20","rust":"stable"}', encoding="utf-8")

    repos = load_candidate_input_repos(tmp_path / "repos.json")
    artifacts = load_candidate_artifact_specs(tmp_path / "artifacts.json")
    toolchain = load_string_pairs_json(tmp_path / "toolchain.json")

    assert isinstance(repos, Ok)
    assert isinstance(artifacts, Ok)
    assert isinstance(toolchain, Ok)
    assert repos.value[0].id == "ms-manager"
    assert artifacts.value[0].filename == "foo.msi"
    assert toolchain.value == (("node", "20"), ("rust", "stable"))


def test_write_and_verify_candidate_bundle_roundtrip(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    import ms.release.flow.candidate_workflow as workflow

    artifacts_dir = tmp_path / "artifacts"
    artifacts_dir.mkdir()
    (artifacts_dir / "foo.msi").write_bytes(b"msi")
    (tmp_path / "package-lock.json").write_text("{}", encoding="utf-8")

    def fake_sign_candidate_manifest(
        *, workspace_root: Path, manifest_path: Path, sig_path: Path, key_env: str
    ):
        del workspace_root, manifest_path, key_env
        sig_path.write_text("sig\n", encoding="utf-8")
        return Ok(None)

    def fake_derive_candidate_public_key(*, workspace_root: Path, key_env: str):
        del workspace_root, key_env
        return Ok("pubkey")

    def fake_verify_candidate_manifest_with_public_key(
        *, workspace_root: Path, manifest_path: Path, sig_path: Path, public_key_b64: str
    ):
        del workspace_root, manifest_path, sig_path, public_key_b64
        return Ok(None)

    def fake_verify_candidate_manifest(
        *, workspace_root: Path, manifest_path: Path, sig_path: Path, pk_env: str
    ):
        del workspace_root, manifest_path, sig_path, pk_env
        return Ok(None)

    monkeypatch.setattr(workflow, "sign_candidate_manifest", fake_sign_candidate_manifest)
    monkeypatch.setattr(workflow, "derive_candidate_public_key", fake_derive_candidate_public_key)
    monkeypatch.setattr(
        workflow,
        "verify_candidate_manifest_with_public_key",
        fake_verify_candidate_manifest_with_public_key,
    )
    monkeypatch.setattr(workflow, "verify_candidate_manifest", fake_verify_candidate_manifest)

    written = write_candidate_bundle(
        workspace_root=tmp_path,
        request=CandidateWriteRequest(
            artifacts_dir=artifacts_dir,
            manifest_path=tmp_path / "candidate.json",
            checksums_path=tmp_path / "checksums.txt",
            sig_path=tmp_path / "candidate.json.sig",
            producer_repo="petitechose-midi-studio/ms-manager",
            producer_kind="ms-manager-app",
            workflow_file=".github/workflows/candidate.yml",
            run_id=1,
            run_attempt=1,
            input_repos=(
                workflow.CandidateInputRepo(
                    id="ms-manager",
                    repo="petitechose-midi-studio/ms-manager",
                    sha="a" * 40,
                ),
            ),
            artifact_specs=(
                CandidateArtifactSpec(
                    id="package-msi",
                    filename="foo.msi",
                    kind="package",
                    os="windows",
                    arch=None,
                ),
            ),
            recipe_base_dir=tmp_path,
            recipe_paths=("package-lock.json",),
            toolchain=(("node", "20"),),
            config=(),
        ),
    )

    assert isinstance(written, Ok)

    verified = verify_candidate_bundle(
        workspace_root=tmp_path,
        request=CandidateVerifyRequest(
            artifacts_dir=artifacts_dir,
            manifest_path=tmp_path / "candidate.json",
            checksums_path=tmp_path / "checksums.txt",
            sig_path=tmp_path / "candidate.json.sig",
            expected_producer_repo="petitechose-midi-studio/ms-manager",
            expected_producer_kind="ms-manager-app",
            expected_workflow_file=".github/workflows/candidate.yml",
            expected_input_repos=(
                workflow.CandidateInputRepo(
                    id="ms-manager",
                    repo="petitechose-midi-studio/ms-manager",
                    sha="a" * 40,
                ),
            ),
        ),
    )

    assert isinstance(verified, Ok)


def test_fetch_candidate_assets_downloads_verifies_and_copies(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    import ms.release.flow.candidate_workflow as workflow

    source_dir = tmp_path / "source"
    source_dir.mkdir()
    (source_dir / "firmware.hex").write_bytes(b"hex")
    (tmp_path / "recipe.txt").write_text("recipe\n", encoding="utf-8")

    seed = bytes(range(32))
    monkeypatch.setenv("MS_CANDIDATE_ED25519_SK", base64.b64encode(seed).decode("ascii"))

    written = write_candidate_bundle(
        workspace_root=tmp_path,
        request=CandidateWriteRequest(
            artifacts_dir=source_dir,
            manifest_path=source_dir / "candidate.json",
            checksums_path=source_dir / "checksums.txt",
            sig_path=source_dir / "candidate.json.sig",
            producer_repo="petitechose-midi-studio/core",
            producer_kind="core-default-firmware",
            workflow_file=".github/workflows/candidate.yml",
            run_id=99,
            run_attempt=1,
            input_repos=(
                workflow.CandidateInputRepo(
                    id="core",
                    repo="petitechose-midi-studio/core",
                    sha="a" * 40,
                ),
            ),
            artifact_specs=(
                CandidateArtifactSpec(
                    id="firmware-default",
                    filename="firmware.hex",
                    kind="firmware",
                    os=None,
                    arch="teensy4.1",
                ),
            ),
            recipe_base_dir=tmp_path,
            recipe_paths=("recipe.txt",),
            toolchain=(("platformio", "6.1.18"),),
            config=(),
        ),
    )
    assert isinstance(written, Ok)

    derived = workflow.derive_candidate_public_key(workspace_root=tmp_path)
    assert isinstance(derived, Ok)

    def fake_resolve_trusted_candidate_producer(
        producer_id: str,
    ) -> Ok[TrustedCandidateProducer]:
        assert producer_id == "core-default-firmware"
        return Ok(
            TrustedCandidateProducer(
                id=producer_id,
                candidate_repo="petitechose-midi-studio/core",
                producer_repo="petitechose-midi-studio/core",
                producer_kind="core-default-firmware",
                workflow_file=".github/workflows/candidate.yml",
                public_key_b64=derived.value,
            )
        )

    def fake_download_release_assets(
        *,
        workspace_root: Path,
        repo: str,
        tag: str,
        out_dir: Path,
    ) -> Ok[Path]:
        del workspace_root, repo, tag
        shutil.copytree(source_dir, out_dir, dirs_exist_ok=True)
        return Ok(out_dir)

    monkeypatch.setattr(
        workflow,
        "resolve_trusted_candidate_producer",
        fake_resolve_trusted_candidate_producer,
    )
    monkeypatch.setattr(workflow, "download_release_assets", fake_download_release_assets)

    output_dir = tmp_path / "out"
    fetched = fetch_candidate_assets(
        workspace_root=tmp_path,
        request=CandidateFetchRequest(
            producer_id="core-default-firmware",
            candidate_tag="rc-" + ("a" * 40),
            output_dir=output_dir,
            asset_filenames=("firmware.hex",),
            expected_input_repos=(
                workflow.CandidateInputRepo(
                    id="core",
                    repo="petitechose-midi-studio/core",
                    sha="a" * 40,
                ),
            ),
        ),
    )

    assert isinstance(fetched, Ok)
    assert fetched.value.copied_files == (output_dir / "firmware.hex",)
    assert (output_dir / "firmware.hex").read_bytes() == b"hex"
