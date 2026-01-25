"""Tests for NinjaTool - validates the tool definition design."""

import sys
from pathlib import Path

import pytest

from ms.core.result import Ok
from ms.platform.detection import Arch, Platform
from ms.tools.base import Mode
from ms.tools.definitions.ninja import NinjaTool
from ms.tools.http import MockHttpClient


class TestNinjaTool:
    """Tests for NinjaTool."""

    def test_spec(self) -> None:
        """NinjaTool has correct spec."""
        tool = NinjaTool()

        assert tool.spec.id == "ninja"
        assert tool.spec.name == "Ninja"
        assert tool.spec.required_for == frozenset({Mode.DEV})
        assert tool.spec.version_args == ("--version",)

    def test_repo(self) -> None:
        """NinjaTool uses correct GitHub repo."""
        tool = NinjaTool()

        assert tool.repo == "ninja-build/ninja"

    def test_install_dir_name(self) -> None:
        """NinjaTool installs to 'ninja' directory."""
        tool = NinjaTool()

        assert tool.install_dir_name() == "ninja"

    def test_strip_components(self) -> None:
        """Ninja archive has no nested directory."""
        tool = NinjaTool()

        assert tool.strip_components() == 0


class TestNinjaToolAssetName:
    """Tests for NinjaTool.asset_name()."""

    def test_linux_x64(self) -> None:
        """Linux x64 asset name."""
        tool = NinjaTool()

        name = tool.asset_name("1.12.1", Platform.LINUX, Arch.X64)

        assert name == "ninja-linux.zip"

    def test_linux_arm64(self) -> None:
        """Linux ARM64 asset name."""
        tool = NinjaTool()

        name = tool.asset_name("1.12.1", Platform.LINUX, Arch.ARM64)

        assert name == "ninja-linux-aarch64.zip"

    def test_macos_x64(self) -> None:
        """macOS x64 asset name (universal binary)."""
        tool = NinjaTool()

        name = tool.asset_name("1.12.1", Platform.MACOS, Arch.X64)

        assert name == "ninja-mac.zip"

    def test_macos_arm64(self) -> None:
        """macOS ARM64 asset name (universal binary)."""
        tool = NinjaTool()

        name = tool.asset_name("1.12.1", Platform.MACOS, Arch.ARM64)

        assert name == "ninja-mac.zip"

    def test_windows(self) -> None:
        """Windows asset name."""
        tool = NinjaTool()

        name = tool.asset_name("1.12.1", Platform.WINDOWS, Arch.X64)

        assert name == "ninja-win.zip"


class TestNinjaToolDownloadUrl:
    """Tests for NinjaTool.download_url()."""

    def test_linux_x64(self) -> None:
        """Full download URL for Linux x64."""
        tool = NinjaTool()

        url = tool.download_url("1.12.1", Platform.LINUX, Arch.X64)

        assert (
            url == "https://github.com/ninja-build/ninja/releases/download/v1.12.1/ninja-linux.zip"
        )

    def test_linux_arm64(self) -> None:
        """Full download URL for Linux ARM64."""
        tool = NinjaTool()

        url = tool.download_url("1.12.1", Platform.LINUX, Arch.ARM64)

        assert (
            url
            == "https://github.com/ninja-build/ninja/releases/download/v1.12.1/ninja-linux-aarch64.zip"
        )

    def test_macos(self) -> None:
        """Full download URL for macOS."""
        tool = NinjaTool()

        url = tool.download_url("1.12.1", Platform.MACOS, Arch.ARM64)

        assert url == "https://github.com/ninja-build/ninja/releases/download/v1.12.1/ninja-mac.zip"

    def test_windows(self) -> None:
        """Full download URL for Windows."""
        tool = NinjaTool()

        url = tool.download_url("1.12.1", Platform.WINDOWS, Arch.X64)

        assert url == "https://github.com/ninja-build/ninja/releases/download/v1.12.1/ninja-win.zip"


class TestNinjaToolBinPath:
    """Tests for NinjaTool.bin_path()."""

    def test_linux(self) -> None:
        """Binary path on Linux."""
        tool = NinjaTool()

        path = tool.bin_path(Path("/tools"), Platform.LINUX)

        assert path == Path("/tools/ninja/ninja")

    def test_macos(self) -> None:
        """Binary path on macOS."""
        tool = NinjaTool()

        path = tool.bin_path(Path("/tools"), Platform.MACOS)

        assert path == Path("/tools/ninja/ninja")

    def test_windows(self) -> None:
        """Binary path on Windows includes .exe."""
        tool = NinjaTool()

        path = tool.bin_path(Path("/tools"), Platform.WINDOWS)

        assert path == Path("/tools/ninja/ninja.exe")


class TestNinjaToolInstallation:
    """Tests for NinjaTool installation methods."""

    def test_is_installed_true(self, tmp_path: Path) -> None:
        """NinjaTool is installed if binary exists."""
        tool = NinjaTool()

        # Create ninja binary
        ninja_dir = tmp_path / "ninja"
        ninja_dir.mkdir()
        ninja = ninja_dir / "ninja"
        ninja.touch()

        assert tool.is_installed(tmp_path, Platform.LINUX) is True

    def test_is_installed_false(self, tmp_path: Path) -> None:
        """NinjaTool is not installed if binary doesn't exist."""
        tool = NinjaTool()

        assert tool.is_installed(tmp_path, Platform.LINUX) is False

    @pytest.mark.skipif(sys.platform == "win32", reason="chmod doesn't work on Windows")
    def test_post_install_unix(self, tmp_path: Path) -> None:
        """Post-install makes ninja executable on Unix."""
        tool = NinjaTool()

        # Create ninja without executable permission
        ninja = tmp_path / "ninja"
        ninja.touch()
        ninja.chmod(0o644)

        tool.post_install(tmp_path, Platform.LINUX)

        # Check executable bit is set
        mode = ninja.stat().st_mode
        assert mode & 0o111

    def test_post_install_windows(self, tmp_path: Path) -> None:
        """Post-install on Windows doesn't fail."""
        tool = NinjaTool()

        # Create ninja.exe
        ninja = tmp_path / "ninja.exe"
        ninja.touch()

        # Should not raise
        tool.post_install(tmp_path, Platform.WINDOWS)


class TestNinjaToolFetchVersion:
    """Tests for NinjaTool.latest_version()."""

    def test_success(self) -> None:
        """Fetch latest version from GitHub."""
        client = MockHttpClient()
        client.set_json(
            "https://api.github.com/repos/ninja-build/ninja/releases/latest",
            {"tag_name": "v1.12.1"},
        )

        tool = NinjaTool()
        result = tool.latest_version(client)

        assert isinstance(result, Ok)
        assert result.value == "1.12.1"

    def test_version_without_v_prefix(self) -> None:
        """Handle version without v prefix."""
        client = MockHttpClient()
        client.set_json(
            "https://api.github.com/repos/ninja-build/ninja/releases/latest",
            {"tag_name": "1.11.0"},
        )

        tool = NinjaTool()
        result = tool.latest_version(client)

        assert isinstance(result, Ok)
        assert result.value == "1.11.0"


@pytest.mark.network
class TestNinjaToolIntegration:
    """Integration tests with real GitHub API.

    Run with: pytest -m network
    """

    def test_fetch_real_version(self) -> None:
        """Fetch real latest version from GitHub."""
        from ms.tools.http import RealHttpClient

        tool = NinjaTool()
        result = tool.latest_version(RealHttpClient())

        assert isinstance(result, Ok)
        # Version should be like "1.12.1"
        version = result.value
        assert version[0].isdigit()
        parts = version.split(".")
        assert len(parts) >= 2
