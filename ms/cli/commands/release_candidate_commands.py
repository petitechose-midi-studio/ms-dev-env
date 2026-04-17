from __future__ import annotations

from pathlib import Path

import typer

from ms.cli.commands.release_common import exit_release, release_error_code
from ms.cli.context import build_context
from ms.core.result import Err, Ok, Result
from ms.release.domain import CandidateInputRepo
from ms.release.errors import ReleaseError
from ms.release.flow.candidate_workflow import (
    CandidateVerifyRequest,
    CandidateWriteRequest,
    load_candidate_artifact_specs,
    load_candidate_input_repos,
    load_string_pairs_json,
    verify_candidate_bundle,
    write_candidate_bundle,
)


def register_candidate_commands(*, namespace: typer.Typer) -> None:
    namespace.command("write")(write_candidate_cmd)
    namespace.command("verify")(verify_candidate_cmd)


def write_candidate_cmd(
    artifacts_dir: Path = typer.Option(
        ..., "--artifacts-dir", help="Directory holding candidate artifacts."
    ),
    artifacts_json: Path = typer.Option(
        ..., "--artifacts-json", help="Artifact metadata JSON array."
    ),
    input_repos_json: Path = typer.Option(
        ..., "--input-repos-json", help="Input repos JSON array."
    ),
    producer_repo: str = typer.Option(..., "--producer-repo", help="Producer repo slug."),
    producer_kind: str = typer.Option(..., "--producer-kind", help="Producer kind identifier."),
    workflow_file: str = typer.Option(
        ..., "--workflow-file", help="Workflow file that produced the candidate."
    ),
    run_id: int = typer.Option(..., "--run-id", min=1, help="GitHub Actions run id."),
    run_attempt: int = typer.Option(
        ..., "--run-attempt", min=1, help="GitHub Actions run attempt."
    ),
    manifest_path: Path = typer.Option(
        ..., "--manifest-path", help="Output candidate manifest path."
    ),
    checksums_path: Path = typer.Option(..., "--checksums-path", help="Output checksums path."),
    sig_path: Path = typer.Option(..., "--sig-path", help="Output signature path."),
    recipe_base_dir: Path = typer.Option(
        ".", "--recipe-base-dir", help="Base directory for recipe paths."
    ),
    recipe_path: list[str] = typer.Option(
        [], "--recipe-path", help="Recipe file path relative to --recipe-base-dir."
    ),
    toolchain_json: Path | None = typer.Option(
        None, "--toolchain-json", help="Optional toolchain JSON object."
    ),
    config_json: Path | None = typer.Option(
        None, "--config-json", help="Optional config JSON object."
    ),
    generated_at: str | None = typer.Option(
        None, "--generated-at", help="Override generated_at RFC3339 timestamp."
    ),
    signing_key_env: str = typer.Option(
        "MS_CANDIDATE_ED25519_SK",
        "--signing-key-env",
        help="Signing secret env var.",
    ),
) -> None:
    ctx = build_context()

    input_repos = _unwrap_or_exit(load_candidate_input_repos(input_repos_json))
    artifacts = _unwrap_or_exit(load_candidate_artifact_specs(artifacts_json))
    toolchain = _unwrap_or_exit(_load_optional_pairs(toolchain_json))
    config = _unwrap_or_exit(_load_optional_pairs(config_json))

    written = write_candidate_bundle(
        workspace_root=ctx.workspace.root,
        request=CandidateWriteRequest(
            artifacts_dir=artifacts_dir,
            manifest_path=manifest_path,
            checksums_path=checksums_path,
            sig_path=sig_path,
            producer_repo=producer_repo,
            producer_kind=producer_kind,
            workflow_file=workflow_file,
            run_id=run_id,
            run_attempt=run_attempt,
            input_repos=input_repos,
            artifact_specs=artifacts,
            recipe_base_dir=recipe_base_dir,
            recipe_paths=tuple(recipe_path),
            toolchain=toolchain,
            config=config,
            generated_at=generated_at,
            signing_key_env=signing_key_env,
        ),
    )
    if isinstance(written, Err):
        exit_release(written.error.pretty(), code=release_error_code(written.error.kind))

    ctx.console.success("Candidate metadata written")
    ctx.console.print(str(manifest_path))


def verify_candidate_cmd(
    artifacts_dir: Path = typer.Option(
        ..., "--artifacts-dir", help="Directory holding candidate artifacts."
    ),
    manifest_path: Path = typer.Option(..., "--manifest-path", help="Candidate manifest path."),
    checksums_path: Path = typer.Option(..., "--checksums-path", help="Checksums path."),
    sig_path: Path = typer.Option(..., "--sig-path", help="Signature path."),
    expected_producer_repo: str | None = typer.Option(
        None, "--expected-producer-repo", help="Expected producer repo."
    ),
    expected_producer_kind: str | None = typer.Option(
        None, "--expected-producer-kind", help="Expected producer kind."
    ),
    expected_workflow_file: str | None = typer.Option(
        None, "--expected-workflow-file", help="Expected workflow file."
    ),
    expected_input_repos_json: Path | None = typer.Option(
        None, "--expected-input-repos-json", help="Expected input repos JSON array."
    ),
    public_key_env: str = typer.Option(
        "MS_CANDIDATE_ED25519_PK", "--public-key-env", help="Public key env var."
    ),
) -> None:
    ctx = build_context()

    expected_repos = _load_expected_input_repos(expected_input_repos_json)

    verified = verify_candidate_bundle(
        workspace_root=ctx.workspace.root,
        request=CandidateVerifyRequest(
            artifacts_dir=artifacts_dir,
            manifest_path=manifest_path,
            checksums_path=checksums_path,
            sig_path=sig_path,
            expected_producer_repo=expected_producer_repo,
            expected_producer_kind=expected_producer_kind,
            expected_workflow_file=expected_workflow_file,
            expected_input_repos=expected_repos,
            public_key_env=public_key_env,
        ),
    )
    if isinstance(verified, Err):
        exit_release(verified.error.pretty(), code=release_error_code(verified.error.kind))

    ctx.console.success("Candidate metadata verified")
    ctx.console.print(verified.value.build_input_fingerprint)


def _load_optional_pairs(path: Path | None) -> Result[tuple[tuple[str, str], ...], ReleaseError]:
    if path is None:
        return Ok(())
    return load_string_pairs_json(path)


def _load_expected_input_repos(path: Path | None) -> tuple[CandidateInputRepo, ...] | None:
    if path is None:
        return None
    return _unwrap_or_exit(load_candidate_input_repos(path))


def _unwrap_or_exit[T](result: Result[T, ReleaseError]) -> T:
    if isinstance(result, Err):
        exit_release(result.error.pretty(), code=release_error_code(result.error.kind))
    return result.value
