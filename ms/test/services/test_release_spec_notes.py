from __future__ import annotations

from pathlib import Path

import pytest

from ms.core.result import Err, Ok
from ms.services.release import notes as notes_mod
from ms.services.release import spec as spec_mod
from ms.services.release.model import PinnedRepo
from ms.services.release.notes import write_release_notes
from ms.services.release.spec import write_release_spec


def _pinned() -> tuple[PinnedRepo, ...]:
    from ms.services.release.config import RELEASE_REPOS

    # Fixed SHAs for tests.
    return tuple(PinnedRepo(repo=r, sha=str(i) * 40) for i, r in enumerate(RELEASE_REPOS))


def test_write_release_spec(tmp_path: Path) -> None:
    pinned = _pinned()
    result = write_release_spec(
        dist_repo_root=tmp_path,
        channel="stable",
        tag="v1.2.3",
        pinned=pinned,
    )
    assert isinstance(result, Ok)
    assert result.value.abs_path.exists()
    text = result.value.abs_path.read_text(encoding="utf-8")
    assert '"schema": 1' in text
    assert '"channel": "stable"' in text
    assert '"tag": "v1.2.3"' in text
    assert "midi-studio-windows-x86_64-bundle.zip" in text
    assert "midi-studio-default-firmware.hex" in text
    assert "midi_studio.bwextension" in text


def test_write_release_notes_includes_pins_and_user_content(tmp_path: Path) -> None:
    pinned = _pinned()
    extra_file = tmp_path / "extra.md"
    extra_file.write_text("Extra section\n", encoding="utf-8")

    result = write_release_notes(
        dist_repo_root=tmp_path,
        channel="beta",
        tag="v1.2.3-beta.1",
        pinned=pinned,
        user_notes="Hello\nWorld",
        user_notes_file=extra_file,
    )
    assert isinstance(result, Ok)
    text = result.value.abs_path.read_text(encoding="utf-8")
    assert "Channel: beta" in text
    assert pinned[0].sha in text
    assert "Hello" in text
    assert "Extra section" in text


def test_write_release_spec_reports_atomic_write_error(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    pinned = _pinned()

    def fail_write(path: Path, content: str, *, encoding: str = "utf-8") -> None:
        del path
        del content
        del encoding
        raise OSError("disk full")

    monkeypatch.setattr(spec_mod, "atomic_write_text", fail_write)
    result = write_release_spec(
        dist_repo_root=tmp_path,
        channel="stable",
        tag="v1.2.3",
        pinned=pinned,
    )
    assert isinstance(result, Err)
    assert result.error.kind == "dist_repo_failed"


def test_write_release_notes_reports_atomic_write_error(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    pinned = _pinned()

    def fail_write(path: Path, content: str, *, encoding: str = "utf-8") -> None:
        del path
        del content
        del encoding
        raise OSError("disk full")

    monkeypatch.setattr(notes_mod, "atomic_write_text", fail_write)
    result = write_release_notes(
        dist_repo_root=tmp_path,
        channel="stable",
        tag="v1.2.3",
        pinned=pinned,
        user_notes=None,
        user_notes_file=None,
    )
    assert isinstance(result, Err)
    assert result.error.kind == "dist_repo_failed"
