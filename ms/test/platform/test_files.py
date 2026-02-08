from __future__ import annotations

import os
from pathlib import Path

import pytest

from ms.platform.files import atomic_write_text


def test_atomic_write_text_creates_parent_dirs(tmp_path: Path) -> None:
    path = tmp_path / "nested" / "state.json"
    atomic_write_text(path, '{"ok":true}\n')

    assert path.exists()
    assert path.read_text(encoding="utf-8") == '{"ok":true}\n'


def test_atomic_write_text_replaces_existing_content(tmp_path: Path) -> None:
    path = tmp_path / "state.json"
    path.write_text("old", encoding="utf-8")

    atomic_write_text(path, "new", encoding="utf-8")

    assert path.read_text(encoding="utf-8") == "new"


def test_atomic_write_text_cleans_temp_file_on_replace_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "state.json"

    def fail_replace(_src: Path, _dst: Path) -> None:
        raise OSError("replace failed")

    monkeypatch.setattr(os, "replace", fail_replace)

    with pytest.raises(OSError, match="replace failed"):
        atomic_write_text(path, "payload", encoding="utf-8")

    leftovers = list(path.parent.glob(f".{path.name}.*.tmp"))
    assert leftovers == []
