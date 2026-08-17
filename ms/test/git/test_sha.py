from __future__ import annotations

from ms.git.sha import is_git_sha


def test_is_git_sha_accepts_only_full_lowercase_hex() -> None:
    assert is_git_sha("a" * 40)
    assert not is_git_sha("a" * 39)
    assert not is_git_sha("g" * 40)
    assert not is_git_sha("A" * 40)
    assert not is_git_sha(None)
