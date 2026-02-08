from __future__ import annotations

from dataclasses import replace

from ms.core.result import Err, Ok, Result
from ms.release.errors import ReleaseError

from .content_contracts import ContentGuidedDependencies
from .menu_option import MenuOption
from .sessions import ContentReleaseSession


def run_content_notes_step(
    *,
    deps: ContentGuidedDependencies,
    session: ContentReleaseSession,
) -> Result[ContentReleaseSession, ReleaseError]:
    options: list[MenuOption[str]] = [
        MenuOption(
            value="keep",
            label=("Keep notes" if session.notes_markdown is not None else "No notes configured"),
            detail=(
                session.notes_path
                if session.notes_path is not None
                else "Provide --notes-file to set notes"
            ),
        )
    ]
    if session.notes_markdown is not None:
        options.append(
            MenuOption(
                value="clear",
                label="Remove notes",
                detail="Publish content release with generated notes only",
            )
        )

    choice = deps.select_menu(
        title="Content Notes",
        subtitle="External notes are optional",
        options=options,
        initial_index=0,
        allow_back=True,
    )
    if choice.action == "cancel":
        return Err(ReleaseError(kind="invalid_input", message="release cancelled"))
    if choice.action == "back":
        return Ok(replace(session, step="summary", return_to_summary=False))
    if choice.value == "clear":
        return Ok(
            replace(
                session,
                notes_path=None,
                notes_markdown=None,
                notes_sha256=None,
                step="summary",
                return_to_summary=False,
            )
        )
    return Ok(replace(session, step="summary", return_to_summary=False))
