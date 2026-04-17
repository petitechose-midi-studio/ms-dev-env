from __future__ import annotations

from pathlib import Path

from pytest import MonkeyPatch

from ms.core.result import Ok
from ms.release.flow.candidate_workflow import (
    CandidateArtifactSpec,
    CandidateVerifyRequest,
    CandidateWriteRequest,
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
