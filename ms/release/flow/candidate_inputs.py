from __future__ import annotations

import json
from pathlib import Path

from ms.core.result import Err, Ok, Result
from ms.core.structured import as_obj_list, as_str_dict, get_str
from ms.release.domain import CandidateInputRepo
from ms.release.errors import ReleaseError

from .candidate_types import CandidateArtifactSpec


def load_candidate_input_repos(path: Path) -> Result[tuple[CandidateInputRepo, ...], ReleaseError]:
    obj = _load_json(path)
    if isinstance(obj, Err):
        return obj
    rows = as_obj_list(obj.value)
    if rows is None:
        return Err(
            ReleaseError(
                kind="invalid_input",
                message=f"candidate input repos must be a JSON array: {path}",
            )
        )

    repos: list[CandidateInputRepo] = []
    for idx, row in enumerate(rows):
        table = as_str_dict(row)
        if table is None:
            return Err(
                ReleaseError(
                    kind="invalid_input",
                    message=f"invalid candidate input repo entry at index {idx}: {path}",
                )
            )
        repo_id = get_str(table, "id")
        repo_slug = get_str(table, "repo")
        sha = get_str(table, "sha")
        if repo_id is None or repo_slug is None or sha is None:
            return Err(
                ReleaseError(
                    kind="invalid_input",
                    message=f"candidate input repos missing fields at index {idx}: {path}",
                )
            )
        repos.append(CandidateInputRepo(id=repo_id, repo=repo_slug, sha=sha))
    return Ok(tuple(repos))


def load_candidate_artifact_specs(
    path: Path,
) -> Result[tuple[CandidateArtifactSpec, ...], ReleaseError]:
    obj = _load_json(path)
    if isinstance(obj, Err):
        return obj
    rows = as_obj_list(obj.value)
    if rows is None:
        return Err(
            ReleaseError(
                kind="invalid_input",
                message=f"candidate artifacts must be a JSON array: {path}",
            )
        )

    specs: list[CandidateArtifactSpec] = []
    for idx, row in enumerate(rows):
        table = as_str_dict(row)
        if table is None:
            return Err(
                ReleaseError(
                    kind="invalid_input",
                    message=f"invalid candidate artifact entry at index {idx}: {path}",
                )
            )
        artifact_id = get_str(table, "id")
        filename = get_str(table, "filename")
        kind = get_str(table, "kind")
        os_name = get_str(table, "os")
        arch = get_str(table, "arch")
        if artifact_id is None or filename is None or kind is None:
            return Err(
                ReleaseError(
                    kind="invalid_input",
                    message=f"candidate artifact missing fields at index {idx}: {path}",
                )
            )
        specs.append(
            CandidateArtifactSpec(
                id=artifact_id,
                filename=filename,
                kind=kind,
                os=os_name,
                arch=arch,
            )
        )
    return Ok(tuple(specs))


def load_string_pairs_json(path: Path) -> Result[tuple[tuple[str, str], ...], ReleaseError]:
    obj = _load_json(path)
    if isinstance(obj, Err):
        return obj
    table = as_str_dict(obj.value)
    if table is None:
        return Err(
            ReleaseError(
                kind="invalid_input",
                message=f"candidate metadata must be a JSON object: {path}",
            )
        )

    out: list[tuple[str, str]] = []
    for key in sorted(table):
        value = get_str(table, key)
        if value is None:
            return Err(
                ReleaseError(
                    kind="invalid_input",
                    message=f"candidate metadata field must be a string: {path}#{key}",
                )
            )
        out.append((key, value))
    return Ok(tuple(out))


def _load_json(path: Path) -> Result[object, ReleaseError]:
    try:
        return Ok(json.loads(path.read_text(encoding="utf-8")))
    except (OSError, json.JSONDecodeError) as e:
        return Err(
            ReleaseError(
                kind="invalid_input",
                message=f"failed to load JSON file: {path}",
                hint=str(e),
            )
        )
