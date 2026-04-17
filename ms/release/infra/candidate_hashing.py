from __future__ import annotations

import hashlib
import json
from pathlib import Path

from ms.core.result import Err, Ok, Result
from ms.release.domain.candidate_models import CandidateInputRepo
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
