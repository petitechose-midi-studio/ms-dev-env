"""Tests for workspace PlatformIO runtime resolution."""

from __future__ import annotations

import os
from pathlib import Path

from ms.core.platformio_runtime import resolve_platformio_runtime
from ms.core.result import Err, Ok


def _make_workspace(tmp_path: Path) -> Path:
    (tmp_path / ".ms-workspace").write_text("")
    return tmp_path


def _venv_python(tools_dir: Path) -> Path:
    venv = tools_dir / "platformio" / "venv"
    if os.name == "nt":
        return venv / "Scripts" / "python.exe"
    return venv / "bin" / "python"


def _create_venv(tools_dir: Path) -> None:
    python = _venv_python(tools_dir)
    python.parent.mkdir(parents=True, exist_ok=True)
    python.write_text("")


class TestResolvePlatformioRuntime:
    def test_custom_tools_dir_is_used(self, tmp_path: Path) -> None:
        workspace = _make_workspace(tmp_path)
        custom = workspace / "custom-tools"
        _create_venv(custom)

        result = resolve_platformio_runtime(workspace, tools_dir=custom)

        assert isinstance(result, Ok)
        assert result.value.python_executable == _venv_python(custom)
        assert result.value.workspace_root == workspace

    def test_custom_tools_dir_missing_reports_error(self, tmp_path: Path) -> None:
        workspace = _make_workspace(tmp_path)
        custom = workspace / "custom-tools"

        result = resolve_platformio_runtime(workspace, tools_dir=custom)

        assert isinstance(result, Err)
        assert "custom-tools" in result.error.message

    def test_default_tools_dir_still_works(self, tmp_path: Path) -> None:
        workspace = _make_workspace(tmp_path)
        _create_venv(workspace / "tools")

        result = resolve_platformio_runtime(workspace)

        assert isinstance(result, Ok)
        assert result.value.python_executable == _venv_python(workspace / "tools")

    def test_no_workspace_falls_back_to_current_python(self, tmp_path: Path) -> None:
        bare = tmp_path / "not-a-workspace"
        bare.mkdir()

        result = resolve_platformio_runtime(bare)

        assert isinstance(result, Ok)
        assert result.value.source == "current_python"
