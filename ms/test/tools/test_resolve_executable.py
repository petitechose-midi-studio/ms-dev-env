"""Tests for ToolRegistry.resolve_executable - bundled tool first, then PATH."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from ms.platform.detection import Platform
from ms.tools.registry import ToolRegistry


def _platform() -> Platform:
    return Platform.WINDOWS if os.name == "nt" else Platform.LINUX


def _write_bundled(tools_dir: Path) -> Path:
    name = "ninja.exe" if os.name == "nt" else "ninja"
    binary = tools_dir / "ninja" / name
    binary.parent.mkdir(parents=True)
    binary.write_bytes(b"bin")
    return binary


def _which_missing(tool_id: str) -> None:
    return None


class TestResolveExecutable:
    def test_bundled_takes_priority(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        tools_dir = tmp_path / "tools"
        bundled = _write_bundled(tools_dir)

        def which_found(tool_id: str) -> str:
            return "C:/other/ninja"

        monkeypatch.setattr("ms.tools.registry.shutil.which", which_found)

        found = ToolRegistry(tools_dir, _platform()).resolve_executable("ninja")

        assert found == bundled

    def test_path_fallback(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        system = tmp_path / "system" / "ninja"
        system.parent.mkdir()
        system.write_bytes(b"bin")

        def which_system(tool_id: str) -> str:
            return str(system)

        monkeypatch.setattr("ms.tools.registry.shutil.which", which_system)

        found = ToolRegistry(tmp_path / "tools", _platform()).resolve_executable("ninja")

        assert found == system

    def test_missing_returns_none(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("ms.tools.registry.shutil.which", _which_missing)

        found = ToolRegistry(tmp_path / "tools", _platform()).resolve_executable("ninja")

        assert found is None
