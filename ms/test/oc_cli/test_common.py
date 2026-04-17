from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path

import pytest

from ms.core.result import Ok
from ms.oc_cli.common import (
    OCPlatform,
    build_pio_env,
    detect_env,
    find_project_root,
    list_serial_ports,
    resolve_pio_runtime,
)


def _platformio_python_path(workspace_root: Path) -> Path:
    if os.name == "nt":
        return workspace_root / "tools" / "platformio" / "venv" / "Scripts" / "python.exe"
    return workspace_root / "tools" / "platformio" / "venv" / "bin" / "python"


def test_find_project_root_walks_up(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = tmp_path / "proj"
    sub = root / "a" / "b"
    sub.mkdir(parents=True)
    (root / "platformio.ini").write_text("[platformio]\n", encoding="utf-8")

    monkeypatch.chdir(sub)
    assert find_project_root() == root


def test_detect_env_prefers_explicit(tmp_path: Path) -> None:
    (tmp_path / "platformio.ini").write_text("default_envs = dev\n", encoding="utf-8")
    assert detect_env(tmp_path, "release") == "release"


def test_detect_env_prefers_latest_build_dir(tmp_path: Path) -> None:
    (tmp_path / "platformio.ini").write_text("default_envs = dev\n", encoding="utf-8")

    build_dir = tmp_path / ".pio" / "build"
    env_a = build_dir / "env-a"
    env_b = build_dir / "env-b"
    env_a.mkdir(parents=True)
    env_b.mkdir(parents=True)

    now = time.time()
    os.utime(env_a, (now - 60, now - 60))
    os.utime(env_b, (now, now))

    assert detect_env(tmp_path, None) == "env-b"


def test_detect_env_falls_back_to_default_envs(tmp_path: Path) -> None:
    (tmp_path / "platformio.ini").write_text("default_envs = release\n", encoding="utf-8")
    assert detect_env(tmp_path, None) == "release"


def test_detect_env_falls_back_to_dev(tmp_path: Path) -> None:
    (tmp_path / "platformio.ini").write_text("[platformio]\n", encoding="utf-8")
    assert detect_env(tmp_path, None) == "dev"


def test_build_pio_env_isolates_platformio_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ws = tmp_path / "ws"
    project = ws / "proj"
    project.mkdir(parents=True)
    (ws / ".ms-workspace").write_text("", encoding="utf-8")

    for k in [
        "PLATFORMIO_CORE_DIR",
        "PLATFORMIO_CACHE_DIR",
        "PLATFORMIO_BUILD_CACHE_DIR",
    ]:
        monkeypatch.delenv(k, raising=False)

    env = build_pio_env(project, OCPlatform())
    assert env["PLATFORMIO_CORE_DIR"].endswith(str(Path(".ms") / "platformio"))
    assert env["PLATFORMIO_CACHE_DIR"].endswith(str(Path(".ms") / "platformio-cache"))
    assert env["PLATFORMIO_BUILD_CACHE_DIR"].endswith(str(Path(".ms") / "platformio-build-cache"))


def test_resolve_pio_runtime_prefers_workspace_python(tmp_path: Path) -> None:
    ws = tmp_path / "ws"
    project = ws / "proj"
    pio_python = _platformio_python_path(ws)
    project.mkdir(parents=True)
    pio_python.parent.mkdir(parents=True)
    pio_python.write_text("", encoding="utf-8")
    (ws / ".ms-workspace").write_text("", encoding="utf-8")

    runtime = resolve_pio_runtime(project)
    assert isinstance(runtime, Ok)
    resolved = runtime.value
    assert resolved.source == "workspace_venv"
    assert resolved.command("run", "--version")[:3] == [
        str(pio_python),
        "-m",
        "platformio",
    ]


def test_list_serial_ports_parses_json_and_filters(monkeypatch: pytest.MonkeyPatch) -> None:
    json_out = '[{"port": "COM1"},{"port": "COM3"},{"port": "/dev/ttyS0"}]'

    def fake_run(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(args=[], returncode=0, stdout=json_out, stderr="")

    monkeypatch.setattr("ms.oc_cli.common.subprocess.run", fake_run)
    ports = list_serial_ports(["python", "-m", "platformio"], env={})
    assert ports == ["COM3"]
