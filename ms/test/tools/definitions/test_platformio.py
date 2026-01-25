"""Tests for PlatformioTool."""

from pathlib import Path

from ms.core.result import Err
from ms.platform.detection import Platform
from ms.tools.base import Mode
from ms.tools.definitions.platformio import PlatformioTool
from ms.tools.http import MockHttpClient


class TestPlatformioTool:
    """Tests for PlatformioTool."""

    def test_spec(self) -> None:
        """PlatformioTool has correct spec."""
        tool = PlatformioTool()

        assert tool.spec.id == "platformio"
        assert tool.spec.name == "PlatformIO"
        assert tool.spec.required_for == frozenset({Mode.DEV})

    def test_install_dir_name(self) -> None:
        """PlatformioTool returns 'platformio' for install_dir_name."""
        tool = PlatformioTool()

        assert tool.install_dir_name() == "platformio"

    def test_bin_path_uses_tools_dir(self, tmp_path: Path) -> None:
        """PlatformioTool uses a dedicated venv under tools/."""
        tool = PlatformioTool()
        tools_dir = tmp_path / "tools"

        p = tool.bin_path(tools_dir, Platform.LINUX)
        assert p == tools_dir / "platformio" / "venv" / "bin" / "pio"


class TestPlatformioToolLatestVersion:
    """Tests for PlatformioTool.latest_version()."""

    def test_returns_error(self) -> None:
        """latest_version returns error (version pinned externally)."""
        client = MockHttpClient()
        tool = PlatformioTool()

        result = tool.latest_version(client)

        assert isinstance(result, Err)
        assert "toolchains.toml" in result.error.message


class TestPlatformioToolBinPath:
    """Tests for PlatformioTool.bin_path()."""

    def test_linux(self) -> None:
        """Binary path on Linux."""
        tool = PlatformioTool()

        path = tool.bin_path(Path("/tools"), Platform.LINUX)
        assert path == Path("/tools") / "platformio" / "venv" / "bin" / "pio"

    def test_macos(self) -> None:
        """Binary path on macOS."""
        tool = PlatformioTool()

        path = tool.bin_path(Path("/tools"), Platform.MACOS)
        assert path == Path("/tools") / "platformio" / "venv" / "bin" / "pio"

    def test_windows(self) -> None:
        """Binary path on Windows uses Scripts and .exe."""
        tool = PlatformioTool()

        path = tool.bin_path(Path("/tools"), Platform.WINDOWS)
        assert path == Path("/tools") / "platformio" / "venv" / "Scripts" / "pio.exe"


class TestPlatformioToolIsInstalled:
    """Tests for PlatformioTool.is_installed()."""

    def test_installed_when_pio_exists(self, tmp_path: Path) -> None:
        """is_installed returns True when pio exists."""
        tool = PlatformioTool()

        tools_dir = tmp_path / "tools"
        pio = tools_dir / "platformio" / "venv" / "bin" / "pio"
        pio.parent.mkdir(parents=True)
        pio.write_text("")

        assert tool.is_installed(tools_dir, Platform.LINUX) is True

    def test_not_installed(self) -> None:
        """is_installed returns False when pio doesn't exist."""
        tool = PlatformioTool()
        assert tool.is_installed(Path("/tools"), Platform.LINUX) is False
