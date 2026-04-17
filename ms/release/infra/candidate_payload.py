from __future__ import annotations

from pathlib import Path

from ms.core.result import Err, Ok, Result
from ms.release.domain.candidate_models import CandidateArtifact, CandidateManifest
from ms.release.errors import ReleaseError

from .candidate_hashing import sha256_file


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
        validated = _validate_artifact(
            artifacts_dir=artifacts_dir,
            artifact=artifact,
            checksums=checksums.value,
        )
        if isinstance(validated, Err):
            return validated

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


def _validate_artifact(
    *,
    artifacts_dir: Path,
    artifact: CandidateArtifact,
    checksums: dict[str, str],
) -> Result[None, ReleaseError]:
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
    checksum = checksums.get(artifact.filename)
    if checksum != artifact.sha256:
        return Err(
            ReleaseError(
                kind="verification_failed",
                message=f"candidate checksums mismatch: {artifact.filename}",
                hint=f"checksums.txt has {checksum!r}",
            )
        )
    return Ok(None)
