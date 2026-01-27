from __future__ import annotations

import os
from pathlib import Path

import pytest

from ms.core.result import Err, Ok
from ms.core.user_workspace import (
    forget_default_workspace_root,
    get_default_workspace_root,
    remember_default_workspace_root,
    user_workspace_config_path,
)
from ms.platform.paths import clear_caches


@pytest.fixture
def isolated_user_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Redirect user_config_dir() to a temp location for tests."""
    if os.name == "nt":
        monkeypatch.setenv("APPDATA", str(tmp_path))
        monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    else:
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
        monkeypatch.delenv("APPDATA", raising=False)

    clear_caches()
    return tmp_path


def test_default_workspace_roundtrip(isolated_user_config: Path, tmp_path: Path) -> None:
    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / ".ms-workspace").write_text("", encoding="utf-8")

    initial = get_default_workspace_root()
    assert isinstance(initial, Ok)
    assert initial.value is None

    saved = remember_default_workspace_root(ws)
    assert isinstance(saved, Ok)

    loaded = get_default_workspace_root()
    assert isinstance(loaded, Ok)
    assert loaded.value == ws.resolve()
    assert user_workspace_config_path().exists()

    cleared = forget_default_workspace_root()
    assert isinstance(cleared, Ok)
    assert not user_workspace_config_path().exists()


def test_invalid_toml_returns_err(isolated_user_config: Path) -> None:
    cfg = user_workspace_config_path()
    cfg.parent.mkdir(parents=True, exist_ok=True)
    cfg.write_text("workspace_root = [\n", encoding="utf-8")

    result = get_default_workspace_root()
    assert isinstance(result, Err)
