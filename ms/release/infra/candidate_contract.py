from __future__ import annotations

import hashlib
import json
from dataclasses import asdict
from pathlib import Path

from ms.core.result import Err, Ok, Result
from ms.core.structured import as_str_dict, get_int, get_list, get_str, get_table
from ms.release.domain.candidate_models import (
    CANDIDATE_SCHEMA,
    CandidateArtifact,
    CandidateInputRepo,
    CandidateManifest,
)
from ms.release.errors import ReleaseError


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256_file(path: Path) -> Result[str, ReleaseError]:
    try:
        with path.open("rb") as handle:
            digest = hashlib.sha256()
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError as e:
        return Err(
            ReleaseError(
                kind="artifact_missing",
                message=f"failed to read file: {path}",
                hint=str(e),
            )
        )
    return Ok(digest.hexdigest())


def describe_candidate_artifact(
    *,
    path: Path,
    artifact_id: str,
    kind: str,
    os_name: str | None = None,
    arch: str | None = None,
) -> Result[CandidateArtifact, ReleaseError]:
    if not path.exists() or not path.is_file():
        return Err(ReleaseError(kind="artifact_missing", message=f"missing artifact file: {path}"))
    digest = sha256_file(path)
    if isinstance(digest, Err):
        return digest
    return Ok(
        CandidateArtifact(
            id=artifact_id,
            filename=path.name,
            kind=kind,
            os=os_name,
            arch=arch,
            size=path.stat().st_size,
            sha256=digest.value,
        )
    )


def compute_recipe_fingerprint(
    *,
    base_dir: Path,
    relative_paths: tuple[str, ...],
) -> Result[str, ReleaseError]:
    digest = hashlib.sha256()
    for rel_path in relative_paths:
        path = base_dir / rel_path
        if not path.exists() or not path.is_file():
            return Err(
                ReleaseError(
                    kind="artifact_missing",
                    message=f"missing recipe path: {rel_path}",
                    hint=str(path),
                )
            )
        file_digest = sha256_file(path)
        if isinstance(file_digest, Err):
            return file_digest
        digest.update(rel_path.encode("utf-8"))
        digest.update(b"\n")
        digest.update(file_digest.value.encode("ascii"))
        digest.update(b"\n")
    return Ok(digest.hexdigest())


def compute_build_input_fingerprint(
    *,
    producer_kind: str,
    input_repos: tuple[CandidateInputRepo, ...],
    recipe_fingerprint: str,
    toolchain: tuple[tuple[str, str], ...] = (),
    config: tuple[tuple[str, str], ...] = (),
    extra: tuple[tuple[str, str], ...] = (),
) -> str:
    normalized = {
        "producer_kind": producer_kind,
        "recipe_fingerprint": recipe_fingerprint,
        "repos": [
            {"id": repo.id, "repo": repo.repo, "sha": repo.sha}
            for repo in sorted(input_repos, key=lambda item: (item.id, item.repo, item.sha))
        ],
        "toolchain": {key: value for key, value in sorted(toolchain)},
        "config": {key: value for key, value in sorted(config)},
        "extra": {key: value for key, value in sorted(extra)},
    }
    encoded = json.dumps(normalized, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def render_candidate_manifest(manifest: CandidateManifest) -> str:
    payload = {
        "schema": manifest.schema,
        "producer_repo": manifest.producer_repo,
        "producer_kind": manifest.producer_kind,
        "workflow_file": manifest.workflow_file,
        "run_id": manifest.run_id,
        "run_attempt": manifest.run_attempt,
        "generated_at": manifest.generated_at,
        "build_input_fingerprint": manifest.build_input_fingerprint,
        "recipe_fingerprint": manifest.recipe_fingerprint,
        "inputs": {
            "repos": [asdict(repo) for repo in manifest.input_repos],
            "toolchain": {key: value for key, value in manifest.toolchain},
            "config": {key: value for key, value in manifest.config},
        },
        "artifacts": [asdict(artifact) for artifact in manifest.artifacts],
    }
    return json.dumps(payload, indent=2, sort_keys=True) + "\n"


def write_candidate_manifest(
    *, path: Path, manifest: CandidateManifest
) -> Result[None, ReleaseError]:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(render_candidate_manifest(manifest), encoding="utf-8")
    except OSError as e:
        return Err(
            ReleaseError(
                kind="repo_failed",
                message=f"failed to write candidate manifest: {path}",
                hint=str(e),
            )
        )
    return Ok(None)


def load_candidate_manifest(path: Path) -> Result[CandidateManifest, ReleaseError]:
    try:
        obj = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        return Err(
            ReleaseError(
                kind="invalid_input",
                message=f"failed to load candidate manifest: {path}",
                hint=str(e),
            )
        )

    table = as_str_dict(obj)
    if table is None:
        return Err(
            ReleaseError(kind="invalid_input", message=f"invalid candidate manifest object: {path}")
        )

    schema = get_str(table, "schema")
    producer_repo = get_str(table, "producer_repo")
    producer_kind = get_str(table, "producer_kind")
    workflow_file = get_str(table, "workflow_file")
    generated_at = get_str(table, "generated_at")
    build_input_fingerprint = get_str(table, "build_input_fingerprint")
    recipe_fingerprint = get_str(table, "recipe_fingerprint")
    run_id = get_int(table, "run_id")
    run_attempt = get_int(table, "run_attempt")
    inputs = get_table(table, "inputs")
    artifacts_raw = get_list(table, "artifacts")

    if (
        schema != CANDIDATE_SCHEMA
        or producer_repo is None
        or producer_kind is None
        or workflow_file is None
        or generated_at is None
        or build_input_fingerprint is None
        or recipe_fingerprint is None
        or run_id is None
        or run_attempt is None
        or inputs is None
        or artifacts_raw is None
    ):
        return Err(
            ReleaseError(
                kind="invalid_input",
                message=f"candidate manifest missing required fields: {path}",
            )
        )

    repos_raw = get_list(inputs, "repos")
    if repos_raw is None:
        return Err(
            ReleaseError(
                kind="invalid_input",
                message=f"candidate manifest missing inputs.repos: {path}",
            )
        )

    repos: list[CandidateInputRepo] = []
    for idx, item in enumerate(repos_raw):
        repo = as_str_dict(item)
        if repo is None:
            return Err(
                ReleaseError(
                    kind="invalid_input",
                    message=f"candidate manifest invalid inputs.repos[{idx}]: {path}",
                )
            )
        repo_id = get_str(repo, "id")
        repo_slug = get_str(repo, "repo")
        sha = get_str(repo, "sha")
        if repo_id is None or repo_slug is None or sha is None:
            return Err(
                ReleaseError(
                    kind="invalid_input",
                    message=f"candidate manifest invalid repo entry at index {idx}: {path}",
                )
            )
        repos.append(CandidateInputRepo(id=repo_id, repo=repo_slug, sha=sha))

    toolchain = _load_key_values(inputs, "toolchain", path)
    if isinstance(toolchain, Err):
        return toolchain
    config = _load_key_values(inputs, "config", path)
    if isinstance(config, Err):
        return config

    artifacts: list[CandidateArtifact] = []
    for idx, item in enumerate(artifacts_raw):
        artifact_table = as_str_dict(item)
        if artifact_table is None:
            return Err(
                ReleaseError(
                    kind="invalid_input",
                    message=f"candidate manifest invalid artifact entry at index {idx}: {path}",
                )
            )
        artifact_id = get_str(artifact_table, "id")
        filename = get_str(artifact_table, "filename")
        kind = get_str(artifact_table, "kind")
        os_name = get_str(artifact_table, "os")
        arch = get_str(artifact_table, "arch")
        size = get_int(artifact_table, "size")
        sha256 = get_str(artifact_table, "sha256")
        if (
            artifact_id is None
            or filename is None
            or kind is None
            or size is None
            or sha256 is None
        ):
            return Err(
                ReleaseError(
                    kind="invalid_input",
                    message=f"candidate manifest invalid artifact fields at index {idx}: {path}",
                )
            )
        artifacts.append(
            CandidateArtifact(
                id=artifact_id,
                filename=filename,
                kind=kind,
                os=os_name,
                arch=arch,
                size=size,
                sha256=sha256,
            )
        )

    return Ok(
        CandidateManifest(
            schema=schema,
            producer_repo=producer_repo,
            producer_kind=producer_kind,
            workflow_file=workflow_file,
            run_id=run_id,
            run_attempt=run_attempt,
            generated_at=generated_at,
            build_input_fingerprint=build_input_fingerprint,
            recipe_fingerprint=recipe_fingerprint,
            input_repos=tuple(repos),
            toolchain=toolchain.value,
            config=config.value,
            artifacts=tuple(artifacts),
        )
    )


def _load_key_values(
    inputs: dict[str, object],
    key: str,
    path: Path,
) -> Result[tuple[tuple[str, str], ...], ReleaseError]:
    obj = inputs.get(key)
    if obj is None:
        return Ok(())
    table = as_str_dict(obj)
    if table is None:
        return Err(
            ReleaseError(
                kind="invalid_input",
                message=f"candidate manifest invalid inputs.{key}: {path}",
            )
        )
    items: list[tuple[str, str]] = []
    for name in sorted(table):
        value = get_str(table, name)
        if value is None:
            return Err(
                ReleaseError(
                    kind="invalid_input",
                    message=f"candidate manifest invalid inputs.{key}.{name}: {path}",
                )
            )
        items.append((name, value))
    return Ok(tuple(items))


def write_candidate_checksums(
    *,
    path: Path,
    manifest: CandidateManifest,
) -> Result[None, ReleaseError]:
    lines = [f"{artifact.sha256}  {artifact.filename}" for artifact in manifest.artifacts]
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
    except OSError as e:
        return Err(
            ReleaseError(
                kind="repo_failed",
                message=f"failed to write candidate checksums: {path}",
                hint=str(e),
            )
        )
    return Ok(None)


def load_candidate_checksums(path: Path) -> Result[dict[str, str], ReleaseError]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as e:
        return Err(
            ReleaseError(
                kind="artifact_missing",
                message=f"failed to read candidate checksums: {path}",
                hint=str(e),
            )
        )

    out: dict[str, str] = {}
    for idx, raw_line in enumerate(lines):
        line = raw_line.strip()
        if not line:
            continue
        parts = raw_line.split("  ", 1)
        if len(parts) != 2:
            return Err(
                ReleaseError(
                    kind="invalid_input",
                    message=f"invalid checksums line {idx + 1}: {path}",
                )
            )
        digest = parts[0].strip()
        filename = parts[1].strip()
        if not digest or not filename:
            return Err(
                ReleaseError(
                    kind="invalid_input",
                    message=f"invalid checksums entry at line {idx + 1}: {path}",
                )
            )
        out[filename] = digest
    return Ok(out)


def validate_candidate_payload(
    *,
    artifacts_dir: Path,
    manifest: CandidateManifest,
    checksums_path: Path,
) -> Result[None, ReleaseError]:
    checksums = load_candidate_checksums(checksums_path)
    if isinstance(checksums, Err):
        return checksums

    for artifact in manifest.artifacts:
        artifact_path = artifacts_dir / artifact.filename
        if not artifact_path.exists() or not artifact_path.is_file():
            return Err(
                ReleaseError(
                    kind="artifact_missing",
                    message=f"candidate artifact missing: {artifact.filename}",
                    hint=str(artifact_path),
                )
            )
        if artifact_path.stat().st_size != artifact.size:
            return Err(
                ReleaseError(
                    kind="verification_failed",
                    message=f"candidate artifact size mismatch: {artifact.filename}",
                    hint=f"expected {artifact.size}, got {artifact_path.stat().st_size}",
                )
            )
        digest = sha256_file(artifact_path)
        if isinstance(digest, Err):
            return digest
        if digest.value != artifact.sha256:
            return Err(
                ReleaseError(
                    kind="verification_failed",
                    message=f"candidate artifact digest mismatch: {artifact.filename}",
                    hint=f"expected {artifact.sha256}, got {digest.value}",
                )
            )
        checksum = checksums.value.get(artifact.filename)
        if checksum != artifact.sha256:
            return Err(
                ReleaseError(
                    kind="verification_failed",
                    message=f"candidate checksums mismatch: {artifact.filename}",
                    hint=f"checksums.txt has {checksum!r}",
                )
            )

    manifest_filenames = {artifact.filename for artifact in manifest.artifacts}
    checksum_filenames = set(checksums.value)
    extra = checksum_filenames - manifest_filenames
    if extra:
        return Err(
            ReleaseError(
                kind="verification_failed",
                message="candidate checksums contain unknown files",
                hint=", ".join(sorted(extra)),
            )
        )

    return Ok(None)
