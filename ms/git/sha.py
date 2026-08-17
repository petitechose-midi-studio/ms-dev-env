from __future__ import annotations

from typing import TypeIs


def is_git_sha(value: object) -> TypeIs[str]:
    return (
        isinstance(value, str)
        and len(value) == 40
        and all(character in "0123456789abcdef" for character in value)
    )
