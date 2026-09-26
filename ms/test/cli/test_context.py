"""Tests for ms.cli.context config propagation."""

from __future__ import annotations

from pathlib import Path

import pytest
import typer

from ms.cli.context import build_context
from ms.core.errors import ErrorCode
from ms.core.result import Ok
from ms.core.workspace import Workspace

_VALID = "[ports]\nhardware = 9500\n"


def _patch_workspace(monkeypatch: pytest.MonkeyPatch, root: Path) -> None:
    monkeypatch.setattr("ms.cli.context.detect_workspace", lambda: Ok(Workspace(root=root)))


def test_valid_config_is_loaded(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    (tmp_path / "config.toml").write_text(_VALID)
    _patch_workspace(monkeypatch, tmp_path)

    context = build_context()

    assert context.config is not None
    assert context.config.ports.hardware == 9500


def test_missing_config_uses_defaults(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _patch_workspace(monkeypatch, tmp_path)

    context = build_context()

    assert context.config.ports.hardware == 9000
    assert context.config.paths.tools == "tools"


def test_invalid_config_exits_with_user_error(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    (tmp_path / "config.toml").write_text("this is not toml [[[")
    _patch_workspace(monkeypatch, tmp_path)

    with pytest.raises(typer.Exit) as exc:
        build_context()

    assert exc.value.exit_code == int(ErrorCode.USER_ERROR)


def test_invalid_port_exits_with_user_error(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    (tmp_path / "config.toml").write_text('[ports]\nnative = "oops"\n')
    _patch_workspace(monkeypatch, tmp_path)

    with pytest.raises(typer.Exit) as exc:
        build_context()

    assert exc.value.exit_code == int(ErrorCode.USER_ERROR)
