from __future__ import annotations

from pathlib import Path

from ms.core.result import Err, Ok
from ms.services.release.notes import load_external_notes_file


def test_load_external_notes_file_ok(tmp_path: Path) -> None:
    notes = tmp_path / "release-notes.md"
    notes.write_text("# Notes\n\n- Added feature\n", encoding="utf-8")

    loaded = load_external_notes_file(path=notes)
    assert isinstance(loaded, Ok)
    assert loaded.value.source_path == notes
    assert loaded.value.markdown.startswith("# Notes")
    assert len(loaded.value.sha256) == 64


def test_load_external_notes_file_rejects_non_md(tmp_path: Path) -> None:
    notes = tmp_path / "release-notes.txt"
    notes.write_text("notes", encoding="utf-8")

    loaded = load_external_notes_file(path=notes)
    assert isinstance(loaded, Err)
    assert loaded.error.kind == "invalid_input"


def test_load_external_notes_file_rejects_empty(tmp_path: Path) -> None:
    notes = tmp_path / "release-notes.md"
    notes.write_text("\n\n", encoding="utf-8")

    loaded = load_external_notes_file(path=notes)
    assert isinstance(loaded, Err)
    assert loaded.error.kind == "invalid_input"
