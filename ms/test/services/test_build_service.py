# pyright: reportPrivateUsage=false

from __future__ import annotations

from pathlib import Path

import pytest

from ms.core.result import Err, Ok, Result
from ms.core.workspace import Workspace
from ms.output.console import MockConsole
from ms.platform.detection import Arch, LinuxDistro, Platform, PlatformInfo
from ms.platform.process import ProcessError
from ms.services.build.service import BuildService
from ms.services.build_errors import BuildError, PrereqMissing


def _service(root: Path) -> BuildService:
    return BuildService(
        workspace=Workspace(root=root),
        platform=PlatformInfo(
            platform=Platform.LINUX,
            arch=Arch.X64,
            distro=LinuxDistro.DEBIAN,
        ),
        config=None,
        console=MockConsole(),
    )


def _windows_service(root: Path) -> BuildService:
    return BuildService(
        workspace=Workspace(root=root),
        platform=PlatformInfo(
            platform=Platform.WINDOWS,
            arch=Arch.X64,
            distro=LinuxDistro.UNKNOWN,
        ),
        config=None,
        console=MockConsole(),
    )


def _prepare_sdl_workspace(root: Path) -> Path:
    core_dir = root / "midi-studio" / "core"
    (core_dir / "sdl").mkdir(parents=True)
    device_support_version = (
        root
        / "midi-studio"
        / "device-support"
        / "src"
        / "ms"
        / "device_support"
        / "v1"
        / "Version.hpp"
    )
    device_support_version.parent.mkdir(parents=True)
    device_support_version.touch()
    (root / "open-control").mkdir()
    return core_dir


def test_build_core_file_tool_configures_and_builds_only_its_target(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    core_dir = tmp_path / "midi-studio" / "core"
    core_dir.mkdir(parents=True)
    (tmp_path / "open-control").mkdir()
    (tmp_path / "midi-studio" / "device-support").mkdir()
    service = _service(tmp_path)
    cmake = tmp_path / "cmake"
    ninja = tmp_path / "ninja"

    def fake_tool_path(_self: BuildService, tool_id: str) -> Result[Path, BuildError]:
        return Ok(cmake if tool_id == "cmake" else ninja)

    def fake_unix_prereqs(_self: BuildService) -> Result[None, BuildError]:
        return Ok(None)

    monkeypatch.setattr(BuildService, "_get_tool_path", fake_tool_path)
    monkeypatch.setattr(BuildService, "_check_unix_native_prereqs", fake_unix_prereqs)

    result = service.build_core_file_tool(dry_run=True)
    output = core_dir / "build" / "core-native" / "ms-core-file-tool"
    assert isinstance(service._console, MockConsole)

    assert result == Ok(output)
    assert f"{cmake} -G Ninja -S {core_dir} -B {output.parent}" in service._console.text
    assert "-DMS_CORE_BUILD_TESTS=OFF" in service._console.text
    assert f"{ninja} -C {output.parent} ms-core-file-tool" in service._console.text


def test_sdl_dependency_cmake_args_are_explicit_workspace_roots(tmp_path: Path) -> None:
    service = _service(tmp_path)

    assert service._sdl_dependency_cmake_args() == [
        f"-DOPEN_CONTROL_FRAMEWORK_DIR={tmp_path / 'open-control' / 'framework'}",
        f"-DOPEN_CONTROL_UI_LVGL_DIR={tmp_path / 'open-control' / 'ui-lvgl'}",
        (f"-DOPEN_CONTROL_UI_COMPONENTS_DIR={tmp_path / 'open-control' / 'ui-lvgl-components'}"),
        f"-DOPEN_CONTROL_HAL_SDL_DIR={tmp_path / 'open-control' / 'hal-sdl'}",
        f"-DOPEN_CONTROL_HAL_NET_DIR={tmp_path / 'open-control' / 'hal-net'}",
        f"-DOPEN_CONTROL_HAL_MIDI_DIR={tmp_path / 'open-control' / 'hal-midi'}",
        f"-DOPEN_CONTROL_NOTE_DIR={tmp_path / 'open-control' / 'note'}",
        f"-DMIDI_STUDIO_UI_DIR={tmp_path / 'midi-studio' / 'ui'}",
        f"-DMS_DEVICE_SUPPORT_DIR={tmp_path / 'midi-studio' / 'device-support'}",
        (f"-DLVGL_DIR={tmp_path / 'midi-studio' / 'core' / '.pio' / 'libdeps' / 'dev' / 'lvgl'}"),
    ]


def test_windows_zig_cmake_args_include_resource_compiler(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    service = _windows_service(tmp_path)

    def fake_zig_wrapper(_name: str) -> Path:
        return tmp_path / "tools" / "bin" / f"{_name}.cmd"

    monkeypatch.setattr(service._registry, "get_zig_wrapper", fake_zig_wrapper)

    assert (
        f"-DCMAKE_RC_COMPILER:FILEPATH={fake_zig_wrapper('zig-rc')}"
        in service._windows_zig_cmake_args()
    )


def test_windows_native_prereqs_require_zig_resource_compiler(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    service = _windows_service(tmp_path)
    wrapper_dir = tmp_path / "tools" / "bin"
    wrapper_dir.mkdir(parents=True)
    for name in ("zig-cc", "zig-cxx", "zig-ar", "zig-ranlib"):
        (wrapper_dir / f"{name}.cmd").touch()

    def fake_zig_wrapper(name: str) -> Path:
        return wrapper_dir / f"{name}.cmd"

    monkeypatch.setattr(service._registry, "get_zig_wrapper", fake_zig_wrapper)

    result = service._check_windows_native_prereqs(require_sdl2=False)

    assert isinstance(result, Err)
    assert isinstance(result.error, PrereqMissing)
    assert result.error.name == "Zig wrapper missing: zig-rc"


def test_build_prereqs_require_device_support_checkout(tmp_path: Path) -> None:
    _prepare_sdl_workspace(tmp_path)
    device_support_version = (
        tmp_path
        / "midi-studio"
        / "device-support"
        / "src"
        / "ms"
        / "device_support"
        / "v1"
        / "Version.hpp"
    )
    device_support_version.unlink()

    result = _service(tmp_path)._check_build_prereqs(dry_run=True)

    assert isinstance(result, Err)
    assert isinstance(result.error, PrereqMissing)
    assert result.error.name == "midi-studio/device-support"
    assert result.error.hint == "Run: uv run ms sync --repos"


def test_build_prereqs_reuse_existing_dev_lvgl(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    core_dir = _prepare_sdl_workspace(tmp_path)
    lvgl_cmake = core_dir / ".pio" / "libdeps" / "dev" / "lvgl" / "CMakeLists.txt"
    lvgl_cmake.parent.mkdir(parents=True)
    lvgl_cmake.touch()
    service = _service(tmp_path)

    def unexpected_platformio(_self: BuildService) -> list[str] | None:
        raise AssertionError("PlatformIO must not run when the dev LVGL checkout exists")

    monkeypatch.setattr(BuildService, "_platformio_cmd", unexpected_platformio)

    assert isinstance(service._check_build_prereqs(dry_run=False), Ok)


def test_build_prereqs_install_platformio_dev_dependencies(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    core_dir = _prepare_sdl_workspace(tmp_path)
    service = _service(tmp_path)
    seen: dict[str, object] = {}

    def fake_platformio(_self: BuildService) -> list[str] | None:
        return ["pio"]

    def fake_run_silent(
        cmd: list[str],
        cwd: Path,
        env: dict[str, str] | None = None,
        *,
        timeout: float | None = None,
    ) -> Result[None, ProcessError]:
        seen.update(cmd=cmd, cwd=cwd, env=env, timeout=timeout)
        lvgl_cmake = core_dir / ".pio" / "libdeps" / "dev" / "lvgl" / "CMakeLists.txt"
        lvgl_cmake.parent.mkdir(parents=True)
        lvgl_cmake.touch()
        return Ok(None)

    monkeypatch.setattr(BuildService, "_platformio_cmd", fake_platformio)
    monkeypatch.setattr("ms.services.build.helpers.run_silent", fake_run_silent)

    assert isinstance(service._check_build_prereqs(dry_run=False), Ok)
    assert seen["cmd"] == ["pio", "pkg", "install", "-e", "dev"]
    assert seen["cwd"] == core_dir
    assert seen["timeout"] == 15 * 60.0
    env = seen["env"]
    assert isinstance(env, dict)
    assert env["PLATFORMIO_CORE_DIR"] == str(tmp_path / ".ms" / "platformio")


def test_build_prereqs_fail_when_install_does_not_supply_lvgl(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _prepare_sdl_workspace(tmp_path)
    service = _service(tmp_path)

    def fake_platformio(_self: BuildService) -> list[str] | None:
        return ["pio"]

    def fake_run_silent(
        cmd: list[str],
        cwd: Path,
        env: dict[str, str] | None = None,
        *,
        timeout: float | None = None,
    ) -> Result[None, ProcessError]:
        del cmd, cwd, env, timeout
        return Ok(None)

    monkeypatch.setattr(BuildService, "_platformio_cmd", fake_platformio)
    monkeypatch.setattr("ms.services.build.helpers.run_silent", fake_run_silent)

    result = service._check_build_prereqs(dry_run=False)

    assert isinstance(result, Err)
    assert isinstance(result.error, PrereqMissing)
    assert result.error.name == "LVGL source"
