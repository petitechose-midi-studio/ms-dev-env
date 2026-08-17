from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

from ms.core.hashing import is_sha256
from ms.core.result import Err, Ok, Result
from ms.core.structured import ObjList, StrDict, as_str_dict, get_int, get_list, get_str, get_table
from ms.git.sha import is_git_sha
from ms.platform.files import atomic_write_text
from ms.release.domain.candidate_models import (
    CANDIDATE_SCHEMA,
    CandidateArtifact,
    CandidateInputRepo,
    CandidateManifest,
)
from ms.release.errors import ReleaseError


@dataclass(frozen=True, slots=True)
class _CandidateHeader:
    producer_repo: str
    producer_kind: str
    workflow_file: str
    run_id: int
    run_attempt: int
    generated_at: str
    build_input_fingerprint: str
    recipe_fingerprint: str


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
        atomic_write_text(path, render_candidate_manifest(manifest), encoding="utf-8")
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

    header = _load_header(table=table, path=path)
    if isinstance(header, Err):
        return header
    inputs = get_table(table, "inputs")
    artifacts_raw = get_list(table, "artifacts")
    if inputs is None or artifacts_raw is None:
        return Err(
            ReleaseError(
                kind="invalid_input",
                message=f"candidate manifest missing required fields: {path}",
            )
        )

    repos = _load_input_repos(inputs=inputs, path=path)
    if isinstance(repos, Err):
        return repos
    toolchain = _load_key_values(inputs=inputs, key="toolchain", path=path)
    if isinstance(toolchain, Err):
        return toolchain
    config = _load_key_values(inputs=inputs, key="config", path=path)
    if isinstance(config, Err):
        return config
    artifacts = _load_artifacts(artifacts_raw=artifacts_raw, path=path)
    if isinstance(artifacts, Err):
        return artifacts

    return Ok(
        CandidateManifest(
            schema=CANDIDATE_SCHEMA,
            producer_repo=header.value.producer_repo,
            producer_kind=header.value.producer_kind,
            workflow_file=header.value.workflow_file,
            run_id=header.value.run_id,
            run_attempt=header.value.run_attempt,
            generated_at=header.value.generated_at,
            build_input_fingerprint=header.value.build_input_fingerprint,
            recipe_fingerprint=header.value.recipe_fingerprint,
            input_repos=repos.value,
            toolchain=toolchain.value,
            config=config.value,
            artifacts=artifacts.value,
        )
    )


def _load_header(*, table: StrDict, path: Path) -> Result[_CandidateHeader, ReleaseError]:
    schema = get_str(table, "schema")
    producer_repo = get_str(table, "producer_repo")
    producer_kind = get_str(table, "producer_kind")
    workflow_file = get_str(table, "workflow_file")
    generated_at = get_str(table, "generated_at")
    build_input_fingerprint = get_str(table, "build_input_fingerprint")
    recipe_fingerprint = get_str(table, "recipe_fingerprint")
    run_id = get_int(table, "run_id")
    run_attempt = get_int(table, "run_attempt")

    if schema != CANDIDATE_SCHEMA:
        return Err(
            ReleaseError(
                kind="invalid_input",
                message=f"unsupported candidate manifest schema: {schema!r}",
                hint=str(path),
            )
        )
    if (
        producer_repo is None
        or producer_kind is None
        or workflow_file is None
        or generated_at is None
    ):
        return Err(
            ReleaseError(
                kind="invalid_input",
                message=f"candidate manifest missing producer fields: {path}",
            )
        )
    if not is_sha256(build_input_fingerprint) or not is_sha256(recipe_fingerprint):
        return Err(
            ReleaseError(
                kind="invalid_input",
                message=f"candidate manifest has invalid fingerprints: {path}",
            )
        )
    if run_id is None or run_id < 1 or run_attempt is None or run_attempt < 1:
        return Err(
            ReleaseError(
                kind="invalid_input",
                message=f"candidate manifest has invalid workflow run identity: {path}",
            )
        )

    return Ok(
        _CandidateHeader(
            producer_repo=producer_repo,
            producer_kind=producer_kind,
            workflow_file=workflow_file,
            run_id=run_id,
            run_attempt=run_attempt,
            generated_at=generated_at,
            build_input_fingerprint=build_input_fingerprint,
            recipe_fingerprint=recipe_fingerprint,
        )
    )


def _load_input_repos(
    *,
    inputs: StrDict,
    path: Path,
) -> Result[tuple[CandidateInputRepo, ...], ReleaseError]:
    repos_raw = get_list(inputs, "repos")
    if repos_raw is None:
        return Err(
            ReleaseError(
                kind="invalid_input",
                message=f"candidate manifest missing inputs.repos: {path}",
            )
        )

    repos: list[CandidateInputRepo] = []
    repo_ids: set[str] = set()
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
        if repo_id is None or repo_slug is None or not is_git_sha(sha) or repo_id in repo_ids:
            return Err(
                ReleaseError(
                    kind="invalid_input",
                    message=f"candidate manifest invalid repo entry at index {idx}: {path}",
                )
            )
        repo_ids.add(repo_id)
        repos.append(CandidateInputRepo(id=repo_id, repo=repo_slug, sha=sha))
    return Ok(tuple(repos))


def _load_key_values(
    *,
    inputs: StrDict,
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


def _load_artifacts(
    *,
    artifacts_raw: ObjList,
    path: Path,
) -> Result[tuple[CandidateArtifact, ...], ReleaseError]:
    artifacts: list[CandidateArtifact] = []
    artifact_ids: set[str] = set()
    filenames: set[str] = set()
    for idx, item in enumerate(artifacts_raw):
        parsed = _load_artifact(item=item, index=idx, path=path)
        if isinstance(parsed, Err):
            return parsed
        artifact = parsed.value
        if artifact.id in artifact_ids or artifact.filename in filenames:
            return Err(
                ReleaseError(
                    kind="invalid_input",
                    message=f"candidate manifest duplicate artifact at index {idx}: {path}",
                )
            )
        artifact_ids.add(artifact.id)
        filenames.add(artifact.filename)
        artifacts.append(artifact)
    return Ok(tuple(artifacts))


def _load_artifact(
    *, item: object, index: int, path: Path
) -> Result[CandidateArtifact, ReleaseError]:
    table = as_str_dict(item)
    if table is None:
        return Err(
            ReleaseError(
                kind="invalid_input",
                message=f"candidate manifest invalid artifact entry at index {index}: {path}",
            )
        )

    artifact_id = get_str(table, "id")
    filename = get_str(table, "filename")
    kind = get_str(table, "kind")
    size = get_int(table, "size")
    sha256 = get_str(table, "sha256")
    if (
        artifact_id is None
        or filename is None
        or kind is None
        or size is None
        or size < 0
        or not is_sha256(sha256)
        or filename in {".", ".."}
        or "/" in filename
        or "\\" in filename
    ):
        return Err(
            ReleaseError(
                kind="invalid_input",
                message=f"candidate manifest invalid artifact fields at index {index}: {path}",
            )
        )

    return Ok(
        CandidateArtifact(
            id=artifact_id,
            filename=filename,
            kind=kind,
            os=get_str(table, "os"),
            arch=get_str(table, "arch"),
            size=size,
            sha256=sha256,
        )
    )
