from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from ms.core.result import Err, Ok, Result
from ms.core.structured import ObjList, StrDict, as_str_dict, get_int, get_list, get_str, get_table
from ms.release.domain.candidate_models import (
    CANDIDATE_SCHEMA,
    CandidateArtifact,
    CandidateInputRepo,
    CandidateManifest,
)
from ms.release.errors import ReleaseError


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
    missing = (
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
    )
    if missing:
        return Err(
            ReleaseError(
                kind="invalid_input",
                message=f"candidate manifest missing required fields: {path}",
            )
        )
    assert schema is not None
    assert producer_repo is not None
    assert producer_kind is not None
    assert workflow_file is not None
    assert generated_at is not None
    assert build_input_fingerprint is not None
    assert recipe_fingerprint is not None
    assert run_id is not None
    assert run_attempt is not None
    assert inputs is not None
    assert artifacts_raw is not None

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
            schema=schema,
            producer_repo=producer_repo,
            producer_kind=producer_kind,
            workflow_file=workflow_file,
            run_id=run_id,
            run_attempt=run_attempt,
            generated_at=generated_at,
            build_input_fingerprint=build_input_fingerprint,
            recipe_fingerprint=recipe_fingerprint,
            input_repos=repos.value,
            toolchain=toolchain.value,
            config=config.value,
            artifacts=artifacts.value,
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
        missing = (
            artifact_id is None
            or filename is None
            or kind is None
            or size is None
            or sha256 is None
        )
        if missing:
            return Err(
                ReleaseError(
                    kind="invalid_input",
                    message=f"candidate manifest invalid artifact fields at index {idx}: {path}",
                )
            )
        assert artifact_id is not None
        assert filename is not None
        assert kind is not None
        assert size is not None
        assert sha256 is not None
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
    return Ok(tuple(artifacts))
