from __future__ import annotations

from dataclasses import replace

from ms.core.result import Err, Ok
from ms.release.flow.guided.notes_transition import apply_notes_selection
from ms.release.flow.guided.selection import Selection
from ms.release.flow.guided.session_models import new_app_session, new_content_session


def test_clear_notes_returns_to_summary() -> None:
    session = replace(
        new_app_session(created_by="test", notes_path=None),
        step="notes",
        notes_path="notes.md",
        notes_markdown="notes",
        notes_sha256="a" * 64,
        return_to_summary=True,
    )

    result = apply_notes_selection(
        session,
        Selection(action="select", value="clear", index=1),
    )

    assert isinstance(result, Ok)
    assert result.value.step == "summary"
    assert result.value.notes_path is None
    assert result.value.notes_markdown is None
    assert result.value.notes_sha256 is None
    assert result.value.return_to_summary is False


def test_keep_notes_preserves_content_notes() -> None:
    session = replace(
        new_content_session(created_by="test", notes_path=None),
        step="notes",
        notes_path="notes.md",
        notes_markdown="notes",
        notes_sha256="b" * 64,
    )

    result = apply_notes_selection(
        session,
        Selection(action="back", value=None, index=0),
    )

    assert isinstance(result, Ok)
    assert result.value.step == "summary"
    assert result.value.notes_path == "notes.md"
    assert result.value.notes_markdown == "notes"
    assert result.value.notes_sha256 == "b" * 64


def test_cancel_notes_returns_error() -> None:
    session = new_app_session(created_by="test", notes_path=None)

    result = apply_notes_selection(
        session,
        Selection(action="cancel", value=None, index=0),
    )

    assert isinstance(result, Err)
    assert result.error.message == "release cancelled"
