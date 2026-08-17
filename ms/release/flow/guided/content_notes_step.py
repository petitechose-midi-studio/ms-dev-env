from __future__ import annotations

from ms.core.result import Result
from ms.release.errors import ReleaseError

from .content_contracts import ContentGuidedDependencies
from .menu_option import MenuOption
from .notes_transition import apply_notes_selection
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
    return apply_notes_selection(session, choice)
