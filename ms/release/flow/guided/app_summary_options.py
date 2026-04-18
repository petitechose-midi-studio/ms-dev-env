from __future__ import annotations

from .menu_option import MenuOption
from .sessions import AppReleaseSession


def build_app_summary_options(session: AppReleaseSession) -> list[MenuOption[str]]:
    notes_label = session.notes_path or "none"
    return [
        MenuOption(value="channel", label=f"Channel: {session.channel}", detail="Edit channel"),
        MenuOption(value="bump", label=f"Bump: {session.bump}", detail="Edit semantic bump"),
        MenuOption(
            value="sha",
            label=f"Source SHA: {(session.repo_sha or 'unset')[:12]}",
            detail="Edit selected source commit",
        ),
        MenuOption(
            value="tag",
            label=f"Tag: {session.tag}",
            detail=f"Version: {session.version} / tooling: {(session.tooling_sha or 'unset')[:12]}",
        ),
        MenuOption(
            value="notes",
            label=f"Notes file: {notes_label}",
            detail="Optional attached notes",
        ),
        MenuOption(
            value="start",
            label="Start release",
            detail="Continue to final confirmation",
        ),
    ]
