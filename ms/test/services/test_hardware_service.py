from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from ms.core.app import App
from ms.core.workspace import Workspace
from ms.output.console import MockConsole
from ms.platform.detection import Arch, LinuxDistro, Platform, PlatformInfo
from ms.services.hardware import HardwareService
from ms.services.hardware.service import _parse_profiles


def _platform() -> PlatformInfo:
    return PlatformInfo(platform=Platform.WINDOWS, arch=Arch.X64, distro=LinuxDistro.UNKNOWN)


def test_hardware_build_invokes_oc_build_module(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    console = MockConsole()
    ws = Workspace(root=tmp_path)
    app_dir = tmp_path / "midi-studio" / "core"
    app_dir.mkdir(parents=True)
    (app_dir / "platformio.ini").write_text("[platformio]\ndefault_envs = dev\n", encoding="utf-8")
    fw = app_dir / ".pio" / "build" / "dev" / "firmware.hex"
    fw.parent.mkdir(parents=True)
    fw.write_bytes(b"deadbeef")
    app = App(name="core", path=app_dir, has_teensy=True)

    seen: dict[str, object] = {}

    def fake_run(
        cmd: list[str], *, cwd: Path, env: dict[str, str]
    ) -> subprocess.CompletedProcess[str]:
        seen["cmd"] = cmd
        seen["cwd"] = cwd
        seen["env"] = env
        return subprocess.CompletedProcess(args=cmd, returncode=0)

    monkeypatch.setattr("ms.services.hardware.subprocess.run", fake_run)

    svc = HardwareService(workspace=ws, platform=_platform(), config=None, console=console)
    result = svc.build(app, env="dev")
    assert result.is_ok()

    cmd = seen["cmd"]
    assert isinstance(cmd, list)
    assert cmd[:3] == [sys.executable, "-m", "ms.oc_cli.oc_build"]
    assert cmd[-1] == "dev"
    assert seen["cwd"] == app_dir

    env = seen["env"]
    assert isinstance(env, dict)
    assert "PLATFORMIO_CORE_DIR" in env
    assert "PLATFORMIO_CACHE_DIR" in env
    assert "PLATFORMIO_BUILD_CACHE_DIR" in env


def test_hardware_build_dry_run_skips_subprocess(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    console = MockConsole()
    ws = Workspace(root=tmp_path)
    app_dir = tmp_path / "midi-studio" / "core"
    app_dir.mkdir(parents=True)
    (app_dir / "platformio.ini").write_text("[platformio]\ndefault_envs = dev\n", encoding="utf-8")
    app = App(name="core", path=app_dir, has_teensy=True)

    called = {"n": 0}

    def fake_run(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        called["n"] += 1
        return subprocess.CompletedProcess(args=[], returncode=0)

    monkeypatch.setattr("ms.services.hardware.subprocess.run", fake_run)

    svc = HardwareService(workspace=ws, platform=_platform(), config=None, console=console)
    result = svc.build(app, env="dev", dry_run=True)
    assert result.is_ok()
    assert called["n"] == 0


def test_profile_discovery_only_exposes_explicit_environment_owner() -> None:
    raw = """[
      ["env:dev", [
        ["custom_ms_manager_profile", "dev"],
        ["custom_ms_manager_label", "Normal"]
      ]],
      ["env:hidden_child", [
        ["custom_ms_manager_profile", "dev"],
        ["custom_ms_manager_label", "Normal"]
      ]],
      ["env:dev_diagnostics", [
        ["custom_ms_manager_profile", "dev_diagnostics"],
        ["custom_ms_manager_label", "Diagnostics"]
      ]]
    ]"""

    assert [(profile.id, profile.label) for profile in _parse_profiles(raw)] == [
        ("dev", "Normal"),
        ("dev_diagnostics", "Diagnostics"),
    ]
