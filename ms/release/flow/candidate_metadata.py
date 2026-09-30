"""Shared candidate metadata completeness check."""

from __future__ import annotations

from pathlib import Path

_REQUIRED_METADATA = ("candidate.json", "checksums.txt", "candidate.json.sig")


def candidate_metadata_complete(metadata_dir: Path) -> bool:
    """True when all candidate metadata files exist in the directory."""
    return all((metadata_dir / name).is_file() for name in _REQUIRED_METADATA)
