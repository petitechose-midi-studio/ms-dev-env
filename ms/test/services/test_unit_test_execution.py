from pathlib import Path

import pytest
from pytest_mock import MockerFixture

from ms.core.result import Err, Ok
from ms.core.workspace import Workspace
from ms.output.console import MockConsole
from ms.platform.detection import Arch, LinuxDistro, Platform, PlatformInfo
from ms.platform.process import ProcessError
from ms.services.unit_testing.catalog import target_groups
from ms.services.unit_testing.dependencies import load_test_dependency_pin
from ms.services.unit_testing.models import UnitTestConfigureFailed, UnitTestFailed
from ms.services.unit_tests import UnitTestService


@pytest.fixture
def service(tmp_path: Path, mocker: MockerFixture) -> UnitTestService:
    workspace = Workspace(root=tmp_path)
    source = workspace.midi_studio_dir / "core"
    source.mkdir(parents=True)
    (source / "CMakeLists.txt").touch()
    bin_dir = tmp_path / "tools" / "bin"
    bin_dir.mkdir(parents=True)
    (bin_dir / "ctest").touch()

    def executable(name: str) -> Path:
        return bin_dir / name

    def system_tool(name: str) -> str:
        return name

    mocker.patch(
        "ms.tools.registry.ToolRegistry.resolve_executable",
        side_effect=executable,
    )
    mocker.patch("ms.services.unit_testing.execution.shutil.which", side_effect=system_tool)
    pin = load_test_dependency_pin("unity")
    assert isinstance(pin, Ok)
    unity = workspace.cache_dir / "test-deps" / "unity" / pin.value.version
    (unity / "src").mkdir(parents=True)
    (unity / "src" / "unity.h").touch()
    (unity / "src" / "unity.c").touch()
    (unity / ".ms-test-dependency").write_text(pin.value.sha256, encoding="utf-8")
    return UnitTestService(
        workspace=workspace,
        platform=PlatformInfo(platform=Platform.LINUX, arch=Arch.X64, distro=LinuxDistro.UNKNOWN),
        config=None,
        console=MockConsole(),
    )


def test_selected_cmake_tests_build_and_run_exact_normalized_names(
    service: UnitTestService, mocker: MockerFixture,
) -> None:
    process = mocker.patch(
        "ms.services.unit_testing.execution.run",
        return_value=Ok(
            "100% tests passed, 0 tests failed out of 2\nTotal Test time (real) = 0.3 sec"
        ),
    )
    result = service.run(target="core", tests=("A+B", "test_C", "A+B"))
    assert isinstance(result, Ok)
    assert len(result.value) == 1
    assert result.value[0].total_tests == 2
    assert result.value[0].runner_seconds == 0.3
    configure, build, test = process.call_args_list
    assert any(arg.startswith("-DMS_UNITY_SOURCE_DIR=") for arg in configure.args[0])
    assert any(arg.startswith("-DMS_CORE_OPEN_CONTROL_ROOT=") for arg in configure.args[0])
    assert build.args[0][-3:] == ["--target", "test_A+B", "test_C"]
    assert test.args[0][-3:] == ["-R", r"^(test_A\+B|test_C)$", "--no-tests=error"]
    assert all(call.kwargs["timeout"] == 20 * 60.0 for call in process.call_args_list)


@pytest.mark.parametrize("failed_stage", [0, 1, 2])
def test_cmake_failure_stops_pipeline_and_preserves_diagnostics(
    service: UnitTestService, mocker: MockerFixture, failed_stage: int,
) -> None:
    process = mocker.patch(
        "ms.services.unit_testing.execution.run",
        side_effect=[Ok("")] * failed_stage + [
            Err(ProcessError(command=("runner",), returncode=23, stdout="out", stderr="err"))
        ],
    )
    result = service.run(target="core")
    assert isinstance(result, Err)
    expected = UnitTestConfigureFailed if failed_stage == 0 else UnitTestFailed
    assert isinstance(result.error, expected)
    assert result.error.returncode == 23
    assert result.error.output == "out\nerr"
    assert process.call_count == failed_stage + 1


def test_all_group_keeps_runner_order_and_batches_cmake_once(
    service: UnitTestService, mocker: MockerFixture,
) -> None:
    process = mocker.patch("ms.services.unit_testing.execution.run", return_value=Ok(""))
    result = service.run(target="all")
    assert isinstance(result, Ok)
    assert tuple(item.name for item in result.value) == target_groups()["all"]
    commands = [call.args[0] for call in process.call_args_list]
    assert [Path(cmd[0]).name for cmd in commands] == [
        "uv", "uv", "cargo", "cargo", "npm", "npm", "cargo", "cargo",
        "cmake", "cmake", "ctest", "ctest", "ctest", "ctest", "ctest",
    ]
    assert commands[7][1:] == ["check", "--locked"]
    assert [cmd[-1] for cmd in commands if Path(cmd[0]).name == "ctest"] == list(
        target_groups()["firmware"]
    )
    cmake_runs = result.value[-5:]
    assert cmake_runs[0].configure_seconds is not None
    assert cmake_runs[0].build_seconds is not None
    assert all(item.configure_seconds == 0 and item.build_seconds == 0 for item in cmake_runs[1:])
