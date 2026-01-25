"""Tests for CargoTool."""

from pathlib import Path
from unittest.mock import patch

from ms.core.result import Err
from ms.platform.detection import Arch, Platform
from ms.tools.base import Mode
from ms.tools.definitions.cargo import CargoTool
from ms.tools.http import MockHttpClient


class TestCargoTool:
    """Tests for CargoTool."""

    def test_spec(self) -> None:
        """CargoTool has correct spec."""
        tool = CargoTool()

        assert tool.spec.id == "cargo"
        assert tool.spec.name == "Cargo (Rust)"
        assert tool.spec.required_for == frozenset({Mode.DEV})

    def test_install_hint(self) -> None:
        """CargoTool has install hint."""
        tool = CargoTool()

        assert "rustup.rs" in tool.install_hint

    def test_is_system_tool(self) -> None:
        """CargoTool is marked as system tool."""
        tool = CargoTool()

        assert tool.is_system_tool() is True


class TestCargoToolLatestVersion:
    """Tests for CargoTool.latest_version()."""

    def test_returns_error(self) -> None:
        """latest_version returns error for system tools."""
        client = MockHttpClient()
        tool = CargoTool()

        result = tool.latest_version(client)

        assert isinstance(result, Err)
        assert "System tool" in result.error.message
        assert "rustup.rs" in result.error.message


class TestCargoToolDownloadUrl:
    """Tests for CargoTool.download_url()."""

    def test_raises_not_implemented(self) -> None:
        """download_url raises NotImplementedError."""
        tool = CargoTool()

        try:
            tool.download_url("1.0.0", Platform.LINUX, Arch.X64)
            assert False, "Should have raised NotImplementedError"
        except NotImplementedError as e:
            assert "system tool" in str(e).lower()
            assert "rustup.rs" in str(e)


class TestCargoToolBinPath:
    """Tests for CargoTool.bin_path()."""

    def test_returns_none(self) -> None:
        """bin_path returns None for system tools."""
        tool = CargoTool()

        path = tool.bin_path(Path("/tools"), Platform.LINUX)

        assert path is None

    def test_returns_none_all_platforms(self) -> None:
        """bin_path returns None for all platforms."""
        tool = CargoTool()

        for platform in [Platform.LINUX, Platform.MACOS, Platform.WINDOWS]:
            path = tool.bin_path(Path("/tools"), platform)
            assert path is None


class TestCargoToolIsInstalled:
    """Tests for CargoTool.is_installed()."""

    def test_installed_when_in_path(self) -> None:
        """is_installed returns True when cargo is in PATH."""
        tool = CargoTool()

        with patch("shutil.which", return_value="/usr/bin/cargo"):
            assert tool.is_installed(Path("/tools"), Platform.LINUX) is True

    def test_not_installed_when_not_in_path(self) -> None:
        """is_installed returns False when cargo is not in PATH."""
        tool = CargoTool()

        with patch("shutil.which", return_value=None):
            assert tool.is_installed(Path("/tools"), Platform.LINUX) is False

    def test_ignores_tools_dir(self) -> None:
        """is_installed ignores the tools_dir parameter."""
        tool = CargoTool()

        with patch("shutil.which", return_value="/usr/bin/cargo"):
            # Should return True regardless of tools_dir
            assert tool.is_installed(Path("/nonexistent"), Platform.LINUX) is True


class TestCargoToolSystemPath:
    """Tests for CargoTool.system_path()."""

    def test_returns_path_when_found(self) -> None:
        """system_path returns Path when cargo is in PATH."""
        tool = CargoTool()

        with patch("shutil.which", return_value="/usr/bin/cargo"):
            path = tool.system_path(Platform.LINUX)
            assert path == Path("/usr/bin/cargo")

    def test_returns_none_when_not_found(self) -> None:
        """system_path returns None when cargo is not in PATH."""
        tool = CargoTool()

        with patch("shutil.which", return_value=None):
            path = tool.system_path(Platform.LINUX)
            assert path is None

    def test_works_on_windows(self) -> None:
        """system_path works on Windows."""
        tool = CargoTool()

        with patch("shutil.which", return_value="C:\\Users\\user\\.cargo\\bin\\cargo.exe"):
            path = tool.system_path(Platform.WINDOWS)
            assert path == Path("C:\\Users\\user\\.cargo\\bin\\cargo.exe")
