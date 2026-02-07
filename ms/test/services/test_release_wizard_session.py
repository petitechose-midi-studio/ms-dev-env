from __future__ import annotations

from pathlib import Path

from ms.core.result import Ok
from ms.services.release.wizard_session import (
    clear_app_session,
    clear_content_session,
    load_app_session,
    load_content_session,
    new_app_session,
    new_content_session,
    save_app_session,
    save_content_session,
)


def test_app_release_session_roundtrip(tmp_path: Path) -> None:
    session = new_app_session(created_by="alice", notes_path=tmp_path / "notes.md")

    saved = save_app_session(workspace_root=tmp_path, session=session)
    assert isinstance(saved, Ok)

    loaded = load_app_session(workspace_root=tmp_path)
    assert isinstance(loaded, Ok)
    assert loaded.value is not None
    assert loaded.value.release_id == session.release_id
    assert loaded.value.created_by == "alice"
    assert loaded.value.product == "app"


def test_clear_app_release_session(tmp_path: Path) -> None:
    session = new_app_session(created_by="alice", notes_path=None)
    assert isinstance(save_app_session(workspace_root=tmp_path, session=session), Ok)

    cleared = clear_app_session(workspace_root=tmp_path)
    assert isinstance(cleared, Ok)

    loaded = load_app_session(workspace_root=tmp_path)
    assert isinstance(loaded, Ok)
    assert loaded.value is None


def test_content_release_session_roundtrip(tmp_path: Path) -> None:
    session = new_content_session(created_by="bob", notes_path=tmp_path / "notes.md")

    saved = save_content_session(workspace_root=tmp_path, session=session)
    assert isinstance(saved, Ok)

    loaded = load_content_session(workspace_root=tmp_path)
    assert isinstance(loaded, Ok)
    assert loaded.value is not None
    assert loaded.value.release_id == session.release_id
    assert loaded.value.created_by == "bob"
    assert loaded.value.product == "content"


def test_clear_content_release_session(tmp_path: Path) -> None:
    session = new_content_session(created_by="bob", notes_path=None)
    assert isinstance(save_content_session(workspace_root=tmp_path, session=session), Ok)

    cleared = clear_content_session(workspace_root=tmp_path)
    assert isinstance(cleared, Ok)

    loaded = load_content_session(workspace_root=tmp_path)
    assert isinstance(loaded, Ok)
    assert loaded.value is None
