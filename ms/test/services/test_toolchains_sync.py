from pathlib import Path

import pytest
from pytest_mock import MockerFixture

from ms.core.config import Config, PathsConfig
from ms.core.result import Err, Ok
from ms.core.workspace import Workspace
from ms.output.console import MockConsole
from ms.platform.detection import Arch, LinuxDistro, Platform, PlatformInfo
from ms.services.toolchains import ToolchainService
from ms.tools.definitions.platformio import PlatformioTool
from ms.tools.pins import ToolPins
from ms.tools.state import get_installed_version, set_installed_version


@pytest.mark.parametrize("state", ["matching", "outdated", "unreadable"])
def test_platformio_sync_checks_persisted_version_before_reusing_installation(
    tmp_path: Path, mocker: MockerFixture, state: str,
) -> None:
    tools_dir = tmp_path / "custom-tools"
    venv = tools_dir / "platformio" / "venv"
    pio = venv / "bin" / "pio"
    pio.parent.mkdir(parents=True)
    pio.touch()
    version = "6.1.18"
    if state == "unreadable":
        # Invalid UTF-8 must be an inspection failure, not an absent version.
        (tools_dir / "state.json").write_bytes(b"\xff")
    else:
        assert isinstance(
            set_installed_version(
                tools_dir, "platformio", version if state == "matching" else "old"
            ),
            Ok,
        )
    mocker.patch("ms.tools.registry.ToolRegistry.tools", return_value=[PlatformioTool()])
    mocker.patch(
        "ms.services.toolchains.sync.ToolPins.load",
        return_value=ToolPins(versions={}, platformio_version=version, checksums={}),
    )
    run = mocker.patch("ms.services.toolchains.helpers.run_process", return_value=Ok(""))
    silent = mocker.patch("ms.services.toolchains.helpers.run_silent", return_value=Ok(None))
    console = MockConsole()
    result = ToolchainService(
        workspace=Workspace(root=tmp_path),
        platform=PlatformInfo(platform=Platform.LINUX, arch=Arch.X64, distro=LinuxDistro.UNKNOWN),
        config=Config(paths=PathsConfig(tools="custom-tools")),
        console=console,
    ).sync_dev()

    if state == "unreadable":
        assert isinstance(result, Err)
        assert "cannot read tool state" in console.text
        run.assert_not_called()
        silent.assert_not_called()
        assert (tools_dir / "state.json").read_bytes() == b"\xff"
    else:
        assert isinstance(result, Ok)
        assert get_installed_version(tools_dir, "platformio") == Ok(version)
        if state == "outdated":
            run.assert_called_once_with(
                [str(venv / "bin" / "python"), "-m", "pip", "install", f"platformio=={version}"],
                cwd=venv, timeout=20 * 60.0,
            )
            silent.assert_called_once()
        else:
            run.assert_not_called()
            silent.assert_not_called()
    assert not (tmp_path / "tools").exists()
