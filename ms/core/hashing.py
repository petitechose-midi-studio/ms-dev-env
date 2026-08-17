from __future__ import annotations

import hashlib
from pathlib import Path
from typing import TypeIs


def is_sha256(value: object) -> TypeIs[str]:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(char in "0123456789abcdef" for char in value)
    )


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


__all__ = ["is_sha256", "sha256_file"]
