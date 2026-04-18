from __future__ import annotations

import re
from pathlib import Path

import typer

from ms.cli.commands.release_common import exit_release, release_error_code
from ms.cli.context import build_context
from ms.core.result import Err, Ok, Result
from ms.release.domain import CandidateInputRepo
from ms.release.errors import ReleaseError
from ms.release.flow.candidate_workflow import (
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
from .release_candidate_workflow_commands import export_plugin_bitwig_firmware_cmd


def register_candidate_commands(*, namespace: typer.Typer) -> None:
    namespace.command("fetch")(fetch_candidate_cmd)
    namespace.command("write")(write_candidate_cmd)
    namespace.command("verify")(verify_candidate_cmd)
    namespace.command("export-plugin-bitwig-firmware", hidden=True)(
        export_plugin_bitwig_firmware_cmd
    )


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


def fetch_candidate_cmd(
    producer_id: str = typer.Option(..., "--producer-id", help="Trusted producer id."),
    candidate_tag: str = typer.Option(..., "--candidate-tag", help="Candidate release tag."),
    out_dir: Path = typer.Option(..., "--out-dir", help="Directory to copy fetched assets into."),
    asset_filename: list[str] = typer.Option(
        [],
        "--asset-filename",
        help="Candidate asset filename to copy into --out-dir.",
    ),
    input_repo: list[str] = typer.Option(
        [],
        "--input-repo",
        help="Expected input repo triplet as id=repo=sha.",
    ),
) -> None:
    ctx = build_context()

    expected_input_repos = _unwrap_or_exit(_parse_candidate_input_repo_args(tuple(input_repo)))
    fetched = fetch_candidate_assets(
        workspace_root=ctx.workspace.root,
        request=CandidateFetchRequest(
            producer_id=producer_id,
            candidate_tag=candidate_tag,
            output_dir=out_dir,
            asset_filenames=tuple(asset_filename),
            expected_input_repos=expected_input_repos,
        ),
    )
    if isinstance(fetched, Err):
        exit_release(fetched.error.pretty(), code=release_error_code(fetched.error.kind))

    ctx.console.success("Candidate assets fetched")
    for path in fetched.value.copied_files:
        ctx.console.print(str(path))


def _load_optional_pairs(path: Path | None) -> Result[tuple[tuple[str, str], ...], ReleaseError]:
    if path is None:
        return Ok(())
    return load_string_pairs_json(path)


def _load_expected_input_repos(path: Path | None) -> tuple[CandidateInputRepo, ...] | None:
    if path is None:
        return None
    return _unwrap_or_exit(load_candidate_input_repos(path))


def _parse_candidate_input_repo_args(
    values: tuple[str, ...],
) -> Result[tuple[CandidateInputRepo, ...], ReleaseError]:
    repos: list[CandidateInputRepo] = []
    for idx, value in enumerate(values):
        repo = _parse_candidate_input_repo_arg(value=value, idx=idx)
        if isinstance(repo, Err):
            return repo
        repos.append(repo.value)
    return Ok(tuple(repos))


def _parse_candidate_input_repo_arg(
    *, value: str, idx: int
) -> Result[CandidateInputRepo, ReleaseError]:
    parts = value.split("=", maxsplit=2)
    if len(parts) != 3:
        return Err(
            ReleaseError(
                kind="invalid_input",
                message=f"invalid --input-repo at index {idx}: {value}",
                hint="expected id=repo=sha",
            )
        )
    repo_id, repo_slug, sha = parts
    if not repo_id or not repo_slug or re.fullmatch(r"[0-9a-f]{40}", sha) is None:
        return Err(
            ReleaseError(
                kind="invalid_input",
                message=f"invalid --input-repo at index {idx}: {value}",
                hint="expected id=repo=40-char lowercase sha",
            )
        )
    return Ok(CandidateInputRepo(id=repo_id, repo=repo_slug, sha=sha))


def _unwrap_or_exit[T](result: Result[T, ReleaseError]) -> T:
    if isinstance(result, Err):
        exit_release(result.error.pretty(), code=release_error_code(result.error.kind))
    return result.value
