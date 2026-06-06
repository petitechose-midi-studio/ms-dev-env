from __future__ import annotations

from ms.git.repository import GitStatus


def dirty_detail(status: GitStatus) -> str:
    parts: list[str] = []
    if status.staged_count:
        parts.append(f"staged={status.staged_count}")
    if status.unstaged_count:
        parts.append(f"unstaged={status.unstaged_count}")
    if status.untracked_count:
        parts.append(f"untracked={status.untracked_count}")
    summary = ", ".join(parts) if parts else "working tree has local changes"
    entries = [f"  {entry.pretty_xy()} {entry.path}" for entry in status.entries]
    if not entries:
        return summary
    return "\n".join((summary, *entries))
