from __future__ import annotations

import json
from pathlib import Path

from ms.core.workspace import Workspace
from ms.platform.detection import Platform
from ms.services.repos.ms_manager_artifacts import (
    render_ms_manager_dev_artifacts,
    write_ms_manager_dev_artifacts,
)


def test_render_ms_manager_dev_artifacts_uses_windows_executable_suffixes() -> None:
    payload = json.loads(render_ms_manager_dev_artifacts(Platform.WINDOWS))

    assert payload["artifacts"]["oc_bridge_exe"] == "../bin/bridge/oc-bridge.exe"
    assert payload["artifacts"]["loader_exe"].endswith("midi-studio-loader.exe")
    assert payload["artifacts"]["ms_core_file_tool"].endswith("ms-core-file-tool.exe")


def test_render_ms_manager_dev_artifacts_uses_unix_executable_names() -> None:
    payload = json.loads(render_ms_manager_dev_artifacts(Platform.LINUX))

    assert payload["artifacts"]["oc_bridge_exe"] == "../bin/bridge/oc-bridge"
    assert payload["artifacts"]["loader_exe"].endswith("midi-studio-loader")
    assert payload["artifacts"]["ms_core_file_tool"].endswith("ms-core-file-tool")


def test_write_ms_manager_dev_artifacts_creates_active_config(tmp_path: Path) -> None:
    workspace = Workspace(root=tmp_path)

    path = write_ms_manager_dev_artifacts(workspace=workspace, platform=Platform.WINDOWS)

    assert path == tmp_path / "ms-manager" / "dev-artifacts.json"
    assert json.loads(path.read_text(encoding="utf-8"))["strict"] is True
