from __future__ import annotations

from pathlib import Path

from ms.core.result import Ok
from ms.services.release.model import PinnedRepo
from ms.services.release.notes import write_release_notes
from ms.services.release.spec import write_release_spec


def _pinned() -> tuple[PinnedRepo, ...]:
    from ms.services.release.config import RELEASE_REPOS

    # Fixed SHAs for tests.
    return (
        PinnedRepo(repo=RELEASE_REPOS[0], sha="0" * 40),
        PinnedRepo(repo=RELEASE_REPOS[1], sha="1" * 40),
    )


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
