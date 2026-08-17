from __future__ import annotations

from dataclasses import replace

from ms.core.result import Err, Ok, Result
from ms.release.errors import ReleaseError

from .selection import Selection
from .session_models import AppReleaseSession, ContentReleaseSession


def apply_notes_selection[SessionT: (AppReleaseSession, ContentReleaseSession)](
    session: SessionT,
    choice: Selection[str],
) -> Result[SessionT, ReleaseError]:
    if choice.action == "cancel":
        return Err(ReleaseError(kind="invalid_input", message="release cancelled"))

    clear = choice.action == "select" and choice.value == "clear"
    return Ok(
        replace(
            session,
            notes_path=None if clear else session.notes_path,
            notes_markdown=None if clear else session.notes_markdown,
            notes_sha256=None if clear else session.notes_sha256,
            step="summary",
            return_to_summary=False,
        )
    )
