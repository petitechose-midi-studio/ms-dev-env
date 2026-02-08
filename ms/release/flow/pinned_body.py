from __future__ import annotations

from collections.abc import Sequence

from ms.release.domain.models import PinnedRepo


def build_pinned_body(*, intro: Sequence[str], pinned: Sequence[PinnedRepo]) -> str:
    lines = [*intro, "", "Pinned SHAs:"]
    lines.extend(f"- {p.repo.id}: {p.sha}" for p in pinned)
    return "\n".join(lines)
