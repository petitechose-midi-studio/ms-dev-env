"""Error types for the release bounded context."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ReleaseError:
    """Canonical release error payload.

    This format is stable across resolve/flow/infra layers and can be rendered
    by view adapters without importing implementation details.
    """

    kind: str
    message: str
    hint: str | None = None

    def pretty(self) -> str:
        if self.hint:
            return f"{self.message} (hint: {self.hint})"
        return self.message
