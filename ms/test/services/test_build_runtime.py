from pathlib import Path
from typing import Literal

import pytest
from pytest_mock import MockerFixture

from ms.core.config import Config
from ms.core.errors import ErrorCode
from ms.core.result import Err, Ok
from ms.core.workspace import Workspace
from ms.output.console import MockConsole
from ms.platform.detection import Arch, LinuxDistro, Platform, PlatformInfo
from ms.platform.process import ProcessError
from ms.services.bridge_headless import HeadlessBridge, spec_for
from ms.services.build.service import BuildService
from ms.services.build_errors import PrereqMissing


def _service(root: Path, config: Config) -> BuildService:
    return BuildService(
        workspace=Workspace(root=root),
        platform=PlatformInfo(platform=Platform.LINUX, arch=Arch.X64, distro=LinuxDistro.DEBIAN),
        config=config,
        console=MockConsole(),
    )


@pytest.mark.parametrize("mode", ["native", "wasm"])
@pytest.mark.parametrize("interrupted", [False, True])
def test_runtime_releases_bridge_after_process_failure_or_interrupt(
    tmp_path: Path, mocker: MockerFixture,
    mode: Literal["native", "wasm"], interrupted: bool,
) -> None:
    config = Config()
    output = tmp_path / "output" / ("app" if mode == "native" else "index.html")
    build = mocker.patch(
        f"ms.services.build.targets.BuildTargets.build_{mode}", return_value=Ok(output),
    )
    bridge = mocker.MagicMock(spec=HeadlessBridge)
    bridge.spec = spec_for(config, app_name="bitwig", mode=mode)
    start = mocker.patch(
        "ms.services.build.runtime.start_headless_bridge", return_value=Ok(bridge),
    )
    process = mocker.patch("ms.services.build.runtime.run_silent")
    if interrupted:
        process.side_effect = KeyboardInterrupt
    else:
        process.return_value = Err(
            ProcessError(command=("app",), returncode=17, stdout="", stderr="failed")
        )
    service = _service(tmp_path, config)

    code = (
        service.run_native(app_name="bitwig") if mode == "native"
        else service.serve_wasm(app_name="bitwig", port=8123)
    )

    assert code == (0 if interrupted else 17)
    build.assert_called_once_with(app_name="bitwig")
    assert start.call_args.kwargs["config"] is config
    assert start.call_args.kwargs["mode"] == mode
    bridge.__enter__.assert_called_once()
    bridge.__exit__.assert_called_once()
    assert process.call_args.kwargs == {"cwd": tmp_path, "timeout": None}
    args = process.call_args.args[0]
    if mode == "native":
        assert args == [str(output), "1053", "--bridge-udp-port", str(bridge.spec.controller_port)]
    else:
        assert args[1:] == ["-m", "http.server", "8123", "-d", str(output.parent)]


@pytest.mark.parametrize("mode", ["native", "wasm"])
def test_failed_build_never_starts_bridge_or_process(
    tmp_path: Path, mocker: MockerFixture, mode: Literal["native", "wasm"],
) -> None:
    mocker.patch(
        f"ms.services.build.targets.BuildTargets.build_{mode}",
        return_value=Err(PrereqMissing(name="toolchain", hint="install tools")),
    )
    start = mocker.patch("ms.services.build.runtime.start_headless_bridge")
    process = mocker.patch("ms.services.build.runtime.run_silent")
    service = _service(tmp_path, Config())
    code = (
        service.run_native(app_name="core") if mode == "native"
        else service.serve_wasm(app_name="core")
    )
    assert code != 0
    start.assert_not_called()
    process.assert_not_called()


def test_wasm_http_port_conflict_does_not_start_bridge(
    tmp_path: Path, mocker: MockerFixture,
) -> None:
    config = Config()
    mocker.patch(
        "ms.services.build.targets.BuildTargets.build_wasm", return_value=Ok(tmp_path / "app.html"),
    )
    start = mocker.patch("ms.services.build.runtime.start_headless_bridge")
    process = mocker.patch("ms.services.build.runtime.run_silent")
    code = _service(tmp_path, config).serve_wasm(
        app_name="bitwig", port=spec_for(config, app_name="bitwig", mode="wasm").controller_port,
    )
    assert code == int(ErrorCode.USER_ERROR)
    start.assert_not_called()
    process.assert_not_called()
