from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch


def _make_workspace(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / ".ms-workspace").write_text("", encoding="utf-8")


def test_wipe_dry_run_does_not_delete(tmp_path: Path) -> None:
    from ms.cli.commands.wipe import wipe

    ws = tmp_path / "ws"
    _make_workspace(ws)
    (ws / ".ms").mkdir()
    (ws / "tools").mkdir()
    (ws / "bin").mkdir()
    (ws / ".build").mkdir()

    with patch.dict(os.environ, {"WORKSPACE_ROOT": str(ws)}):
        wipe(yes=False)

    assert (ws / ".ms").exists()
    assert (ws / "tools").exists()
    assert (ws / "bin").exists()
    assert (ws / ".build").exists()


def test_wipe_execute_deletes_dirs(tmp_path: Path) -> None:
    from ms.cli.commands.wipe import wipe

    ws = tmp_path / "ws"
    _make_workspace(ws)
    (ws / ".ms").mkdir()
    (ws / "tools").mkdir()
    (ws / "bin").mkdir()
    (ws / ".build").mkdir()

    with patch.dict(os.environ, {"WORKSPACE_ROOT": str(ws)}):
        wipe(yes=True)

    assert not (ws / ".ms").exists()
    assert not (ws / "tools").exists()
    assert not (ws / "bin").exists()
    assert not (ws / ".build").exists()


def test_destroy_dry_run_does_not_delete(tmp_path: Path) -> None:
    from ms.cli.commands.wipe import destroy

    ws = tmp_path / "ws"
    _make_workspace(ws)

    with patch.dict(os.environ, {"WORKSPACE_ROOT": str(ws)}):
        destroy(yes=False)

    assert ws.exists()


def test_destroy_execute_deletes_workspace(tmp_path: Path) -> None:
    from ms.cli.commands.wipe import destroy

    ws = tmp_path / "ws"
    _make_workspace(ws)
    (ws / "tools").mkdir()

    with patch.dict(os.environ, {"WORKSPACE_ROOT": str(ws)}):
        destroy(yes=True)

    assert not ws.exists()
