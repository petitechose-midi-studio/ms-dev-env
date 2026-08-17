from __future__ import annotations

import hashlib
from pathlib import Path

from ms.core.hashing import is_sha256, sha256_file


def test_is_sha256_accepts_only_canonical_digest() -> None:
    assert is_sha256("a" * 64)
    assert not is_sha256("A" * 64)
    assert not is_sha256("g" * 64)
    assert not is_sha256("a" * 63)
    assert not is_sha256(None)


def test_sha256_file_matches_hashlib(tmp_path: Path) -> None:
    path = tmp_path / "payload"
    path.write_bytes(b"checksum-test-bytes")

    assert sha256_file(path) == hashlib.sha256(b"checksum-test-bytes").hexdigest()
