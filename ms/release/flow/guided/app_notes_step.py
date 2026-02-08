from __future__ import annotations

from dataclasses import replace

from ms.core.result import Err, Ok, Result
from ms.release.errors import ReleaseError

from .app_contracts import AppGuidedDependencies, AppPrepareResultLike
from .menu_option import MenuOption
from .sessions import AppReleaseSession


def run_app_notes_step[PrepareT: AppPrepareResultLike](
    *,
    deps: AppGuidedDependencies[PrepareT],
    session: AppReleaseSession,
) -> Result[AppReleaseSession, ReleaseError]:
    choice = deps.select_menu(
        title="Release Notes",
        subtitle="External notes are optional and prepended above auto-notes",
        options=[
            MenuOption(
                value="keep",
                label=(
                    "Keep notes" if session.notes_markdown is not None else "No notes configured"
                ),
                detail=(
                    session.notes_path
                    if session.notes_path is not None
                    else "Provide --notes-file to set notes"
                ),
            ),
            *(
                [
                    MenuOption(
                        value="clear",
                        label="Remove notes",
                        detail="Publish release with automatic notes only",
                    )
                ]
                if session.notes_markdown is not None
                else []
            ),
        ],
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
