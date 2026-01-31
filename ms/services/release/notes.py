from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ms.core.result import Err, Ok, Result
from ms.services.release.config import DIST_NOTES_DIR
from ms.services.release.errors import ReleaseError
from ms.services.release.model import PinnedRepo, ReleaseChannel


@dataclass(frozen=True, slots=True)
class WrittenNotes:
    rel_path: str
    abs_path: Path


def notes_path_for_tag(tag: str) -> str:
    return f"{DIST_NOTES_DIR}/{tag}.md"


def _repo_commit_url(slug: str, sha: str) -> str:
    return f"https://github.com/{slug}/commit/{sha}"


def _render_notes(
    *,
    channel: ReleaseChannel,
    tag: str,
    pinned: tuple[PinnedRepo, ...],
    user_notes: str | None,
    user_notes_file: Path | None,
) -> Result[str, ReleaseError]:
    lines: list[str] = []
    lines.append(f"# {tag}")
    lines.append("")
    lines.append(f"Channel: {channel}")
    lines.append("")

    lines.append("## Pinned Repos")
    for p in pinned:
        url = _repo_commit_url(p.repo.slug, p.sha)
        lines.append(f"- {p.repo.id}: {p.sha} ({url})")

    if user_notes is not None and user_notes.strip():
        lines.append("")
        lines.append("## Notes")
        lines.append(user_notes.rstrip())

    if user_notes_file is not None:
        try:
            extra = user_notes_file.read_text(encoding="utf-8")
        except OSError as e:
            return Err(
                ReleaseError(
                    kind="invalid_input",
                    message=f"failed to read --notes-file: {e}",
                    hint=str(user_notes_file),
                )
            )

        if extra.strip():
            lines.append("")
            lines.append("## Additional")
            lines.append(extra.rstrip())

    return Ok("\n".join(lines).rstrip() + "\n")


def write_release_notes(
    *,
    dist_repo_root: Path,
    channel: ReleaseChannel,
    tag: str,
    pinned: tuple[PinnedRepo, ...],
    user_notes: str | None,
    user_notes_file: Path | None,
) -> Result[WrittenNotes, ReleaseError]:
    rel = notes_path_for_tag(tag)
    path = dist_repo_root / rel
    path.parent.mkdir(parents=True, exist_ok=True)

    rendered = _render_notes(
        channel=channel,
        tag=tag,
        pinned=pinned,
        user_notes=user_notes,
        user_notes_file=user_notes_file,
    )
    if isinstance(rendered, Err):
        return rendered

    try:
        path.write_text(rendered.value, encoding="utf-8")
    except OSError as e:
        return Err(
            ReleaseError(
                kind="dist_repo_failed",
                message=f"failed to write release notes: {e}",
                hint=str(path),
            )
        )

    return Ok(WrittenNotes(rel_path=rel, abs_path=path))
