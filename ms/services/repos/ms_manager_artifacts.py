from __future__ import annotations

import json
from pathlib import Path

from ms.core.workspace import Workspace
from ms.platform.detection import Platform
from ms.platform.files import atomic_write_text

MS_MANAGER_REPO_PATH = "ms-manager"
MS_MANAGER_DEV_ARTIFACTS_FILE = "dev-artifacts.json"


def render_ms_manager_dev_artifacts(platform: Platform) -> str:
    exe_suffix = platform.exe_suffix
    payload = {
        "schema": 1,
        "strict": True,
        "artifacts": {
            "oc_bridge_exe": f"../bin/bridge/oc-bridge{exe_suffix}",
            "loader_exe": (
                f"../midi-studio/loader/target/release/midi-studio-loader{exe_suffix}"
            ),
            "ms_core_file_tool": (
                f"../midi-studio/core/build/core-native/ms-core-file-tool{exe_suffix}"
            ),
            "firmware_standalone": "../bin/core/teensy/dev/firmware.hex",
            "firmware_bitwig": "../bin/bitwig/teensy/dev/firmware.hex",
            "bitwig_extension": "../bin/bitwig/midi_studio.bwextension",
        },
    }
    return json.dumps(payload, indent=2) + "\n"


def write_ms_manager_dev_artifacts(*, workspace: Workspace, platform: Platform) -> Path:
    path = workspace.root / MS_MANAGER_REPO_PATH / MS_MANAGER_DEV_ARTIFACTS_FILE
    atomic_write_text(path, render_ms_manager_dev_artifacts(platform), encoding="utf-8")
    return path
