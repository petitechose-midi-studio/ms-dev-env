"""Tests for BunTool."""

import sys
from pathlib import Path

import pytest

from ms.core.result import Ok
from ms.platform.detection import Arch, Platform
from ms.tools.base import Mode
from ms.tools.definitions.bun import BunTool
from ms.tools.http import MockHttpClient


class TestBunTool:
    """Tests for BunTool."""

    def test_spec(self) -> None:
        """BunTool has correct spec."""
        tool = BunTool()

        assert tool.spec.id == "bun"
        assert tool.spec.name == "Bun"
        assert tool.spec.required_for == frozenset({Mode.DEV})

    def test_repo(self) -> None:
        """BunTool uses correct GitHub repo."""
        tool = BunTool()

        assert tool.repo == "oven-sh/bun"

    def test_install_dir_name(self) -> None:
        """BunTool installs to 'bun' directory."""
        tool = BunTool()

        assert tool.install_dir_name() == "bun"

    def test_strip_components(self) -> None:
        """Bun archive has root directory to strip."""
        tool = BunTool()

        assert tool.strip_components() == 1


class TestBunToolLatestVersion:
    """Tests for BunTool.latest_version()."""

    def test_success_strips_bun_prefix(self) -> None:
        """Fetch latest version and strip bun- prefix."""
        client = MockHttpClient()
        client.set_json(
            "https://api.github.com/repos/oven-sh/bun/releases/latest",
            {"tag_name": "bun-v1.1.30"},
        )

        tool = BunTool()
        result = tool.latest_version(client)

        assert isinstance(result, Ok)
        # Should strip both "v" (by github_latest_release) and "bun-" (by BunTool)
        assert result.value == "1.1.30"

    def test_success_without_bun_prefix(self) -> None:
        """Handle version without bun- prefix."""
        client = MockHttpClient()
        client.set_json(
            "https://api.github.com/repos/oven-sh/bun/releases/latest",
            {"tag_name": "v1.1.30"},
        )

        tool = BunTool()
        result = tool.latest_version(client)

        assert isinstance(result, Ok)
        assert result.value == "1.1.30"


class TestBunToolDownloadUrl:
    """Tests for BunTool.download_url()."""

    def test_linux_x64(self) -> None:
        """Download URL for Linux x64."""
        tool = BunTool()

        url = tool.download_url("1.1.30", Platform.LINUX, Arch.X64)

        assert url == (
            "https://github.com/oven-sh/bun/releases/download/bun-v1.1.30/bun-linux-x64.zip"
        )

    def test_linux_arm64(self) -> None:
        """Download URL for Linux ARM64."""
        tool = BunTool()

        url = tool.download_url("1.1.30", Platform.LINUX, Arch.ARM64)

        assert url == (
            "https://github.com/oven-sh/bun/releases/download/bun-v1.1.30/bun-linux-aarch64.zip"
        )

    def test_macos_x64(self) -> None:
        """Download URL for macOS x64."""
        tool = BunTool()

        url = tool.download_url("1.1.30", Platform.MACOS, Arch.X64)

        assert url == (
            "https://github.com/oven-sh/bun/releases/download/bun-v1.1.30/bun-darwin-x64.zip"
        )

    def test_macos_arm64(self) -> None:
        """Download URL for macOS ARM64."""
        tool = BunTool()

        url = tool.download_url("1.1.30", Platform.MACOS, Arch.ARM64)

        assert url == (
            "https://github.com/oven-sh/bun/releases/download/bun-v1.1.30/bun-darwin-aarch64.zip"
        )

    def test_windows(self) -> None:
        """Download URL for Windows."""
        tool = BunTool()

        url = tool.download_url("1.1.30", Platform.WINDOWS, Arch.X64)

        assert url == (
            "https://github.com/oven-sh/bun/releases/download/bun-v1.1.30/bun-windows-x64.zip"
        )


class TestBunToolBinPath:
    """Tests for BunTool.bin_path()."""

    def test_linux(self) -> None:
        """Binary path on Linux."""
        tool = BunTool()

        path = tool.bin_path(Path("/tools"), Platform.LINUX)

        assert path == Path("/tools/bun/bun")

    def test_macos(self) -> None:
        """Binary path on macOS."""
        tool = BunTool()

        path = tool.bin_path(Path("/tools"), Platform.MACOS)

        assert path == Path("/tools/bun/bun")

    def test_windows(self) -> None:
        """Binary path on Windows includes .exe."""
        tool = BunTool()

        path = tool.bin_path(Path("/tools"), Platform.WINDOWS)

        assert path == Path("/tools/bun/bun.exe")


class TestBunToolInstallation:
    """Tests for BunTool installation methods."""

    def test_is_installed_true(self, tmp_path: Path) -> None:
        """BunTool is installed if binary exists."""
        tool = BunTool()

        # Create bun binary
        bun_dir = tmp_path / "bun"
        bun_dir.mkdir()
        (bun_dir / "bun").touch()

        assert tool.is_installed(tmp_path, Platform.LINUX) is True

    def test_is_installed_false(self, tmp_path: Path) -> None:
        """BunTool is not installed if binary doesn't exist."""
        tool = BunTool()

        assert tool.is_installed(tmp_path, Platform.LINUX) is False

    @pytest.mark.skipif(sys.platform == "win32", reason="chmod doesn't work on Windows")
    def test_post_install_unix(self, tmp_path: Path) -> None:
        """Post-install makes bun executable on Unix."""
        tool = BunTool()

        bun = tmp_path / "bun"
        bun.touch()
        bun.chmod(0o644)

        tool.post_install(tmp_path, Platform.LINUX)

        mode = bun.stat().st_mode
        assert mode & 0o111

    def test_post_install_windows(self, tmp_path: Path) -> None:
        """Post-install on Windows doesn't fail."""
        tool = BunTool()

        bun = tmp_path / "bun.exe"
        bun.touch()

        # Should not raise
        tool.post_install(tmp_path, Platform.WINDOWS)
