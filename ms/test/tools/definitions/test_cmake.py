"""Tests for CMakeTool."""

from pathlib import Path

from ms.core.result import Ok
from ms.platform.detection import Arch, Platform
from ms.tools.base import Mode
from ms.tools.definitions.cmake import CMakeTool
from ms.tools.http import MockHttpClient


class TestCMakeTool:
    """Tests for CMakeTool."""

    def test_spec(self) -> None:
        """CMakeTool has correct spec."""
        tool = CMakeTool()

        assert tool.spec.id == "cmake"
        assert tool.spec.name == "CMake"
        assert tool.spec.required_for == frozenset({Mode.DEV})

    def test_repo(self) -> None:
        """CMakeTool uses correct GitHub repo."""
        tool = CMakeTool()

        assert tool.repo == "Kitware/CMake"

    def test_install_dir_name(self) -> None:
        """CMakeTool installs to 'cmake' directory."""
        tool = CMakeTool()

        assert tool.install_dir_name() == "cmake"

    def test_strip_components(self) -> None:
        """CMake archive has root directory to strip."""
        tool = CMakeTool()

        assert tool.strip_components() == 1


class TestCMakeToolAssetName:
    """Tests for CMakeTool.asset_name()."""

    def test_linux_x64(self) -> None:
        """Linux x64 asset name."""
        tool = CMakeTool()

        name = tool.asset_name("3.31.0", Platform.LINUX, Arch.X64)

        assert name == "cmake-3.31.0-linux-x86_64.tar.gz"

    def test_linux_arm64(self) -> None:
        """Linux ARM64 asset name."""
        tool = CMakeTool()

        name = tool.asset_name("3.31.0", Platform.LINUX, Arch.ARM64)

        assert name == "cmake-3.31.0-linux-aarch64.tar.gz"

    def test_macos(self) -> None:
        """macOS asset name (universal binary)."""
        tool = CMakeTool()

        name = tool.asset_name("3.31.0", Platform.MACOS, Arch.ARM64)

        assert name == "cmake-3.31.0-macos-universal.tar.gz"

    def test_windows(self) -> None:
        """Windows asset name."""
        tool = CMakeTool()

        name = tool.asset_name("3.31.0", Platform.WINDOWS, Arch.X64)

        assert name == "cmake-3.31.0-windows-x86_64.zip"


class TestCMakeToolDownloadUrl:
    """Tests for CMakeTool.download_url()."""

    def test_linux_x64(self) -> None:
        """Full download URL for Linux x64."""
        tool = CMakeTool()

        url = tool.download_url("3.31.0", Platform.LINUX, Arch.X64)

        assert url == (
            "https://github.com/Kitware/CMake/releases/download/"
            "v3.31.0/cmake-3.31.0-linux-x86_64.tar.gz"
        )

    def test_macos(self) -> None:
        """Full download URL for macOS."""
        tool = CMakeTool()

        url = tool.download_url("3.31.0", Platform.MACOS, Arch.ARM64)

        assert url == (
            "https://github.com/Kitware/CMake/releases/download/"
            "v3.31.0/cmake-3.31.0-macos-universal.tar.gz"
        )

    def test_windows(self) -> None:
        """Full download URL for Windows."""
        tool = CMakeTool()

        url = tool.download_url("3.31.0", Platform.WINDOWS, Arch.X64)

        assert url == (
            "https://github.com/Kitware/CMake/releases/download/"
            "v3.31.0/cmake-3.31.0-windows-x86_64.zip"
        )


class TestCMakeToolBinPath:
    """Tests for CMakeTool.bin_path()."""

    def test_linux(self) -> None:
        """Binary path on Linux."""
        tool = CMakeTool()

        path = tool.bin_path(Path("/tools"), Platform.LINUX)

        assert path == Path("/tools/cmake/bin/cmake")

    def test_macos(self) -> None:
        """Binary path on macOS."""
        tool = CMakeTool()

        path = tool.bin_path(Path("/tools"), Platform.MACOS)

        assert path == Path("/tools/cmake/bin/cmake")

    def test_windows(self) -> None:
        """Binary path on Windows includes .exe."""
        tool = CMakeTool()

        path = tool.bin_path(Path("/tools"), Platform.WINDOWS)

        assert path == Path("/tools/cmake/bin/cmake.exe")


class TestCMakeToolInstallation:
    """Tests for CMakeTool installation methods."""

    def test_is_installed_true(self, tmp_path: Path) -> None:
        """CMakeTool is installed if binary exists."""
        tool = CMakeTool()

        # Create cmake binary in bin/
        cmake_bin = tmp_path / "cmake" / "bin"
        cmake_bin.mkdir(parents=True)
        (cmake_bin / "cmake").touch()

        assert tool.is_installed(tmp_path, Platform.LINUX) is True

    def test_is_installed_false(self, tmp_path: Path) -> None:
        """CMakeTool is not installed if binary doesn't exist."""
        tool = CMakeTool()

        assert tool.is_installed(tmp_path, Platform.LINUX) is False

    def test_post_install_macos_app_bundle(self, tmp_path: Path) -> None:
        """Post-install extracts macOS .app bundle."""
        tool = CMakeTool()

        # Create simulated .app bundle structure
        install_dir = tmp_path / "cmake"
        install_dir.mkdir()

        app_contents = install_dir / "CMake.app" / "Contents"
        app_contents.mkdir(parents=True)

        # Create bin/ and share/ inside Contents
        (app_contents / "bin").mkdir()
        (app_contents / "bin" / "cmake").write_text("#!/bin/bash\necho cmake")
        (app_contents / "share").mkdir()
        (app_contents / "share" / "cmake-3.31").mkdir()

        # Run post_install
        tool.post_install(install_dir, Platform.MACOS)

        # Verify .app bundle is gone
        assert not (install_dir / "CMake.app").exists()

        # Verify contents were moved
        assert (install_dir / "bin" / "cmake").exists()
        assert (install_dir / "share" / "cmake-3.31").exists()

    def test_post_install_linux(self, tmp_path: Path) -> None:
        """Post-install on Linux just sets executable bit."""
        tool = CMakeTool()

        # Create cmake binary
        tools_dir = tmp_path / "tools"
        cmake_bin = tools_dir / "cmake" / "bin"
        cmake_bin.mkdir(parents=True)
        cmake = cmake_bin / "cmake"
        cmake.touch()

        # install_dir is tools_dir / "cmake" in the real flow
        install_dir = tools_dir / "cmake"

        # Run post_install (should not fail without .app bundle)
        tool.post_install(install_dir, Platform.LINUX)

        # Binary should exist
        assert cmake.exists()

    def test_post_install_no_app_bundle(self, tmp_path: Path) -> None:
        """Post-install on macOS without .app bundle doesn't fail."""
        tool = CMakeTool()

        install_dir = tmp_path / "cmake"
        install_dir.mkdir()

        # No .app bundle, just bin/
        (install_dir / "bin").mkdir()
        (install_dir / "bin" / "cmake").touch()

        # Should not raise
        tool.post_install(install_dir, Platform.MACOS)


class TestCMakeToolFetchVersion:
    """Tests for CMakeTool.latest_version()."""

    def test_success(self) -> None:
        """Fetch latest version from GitHub."""
        client = MockHttpClient()
        client.set_json(
            "https://api.github.com/repos/Kitware/CMake/releases/latest",
            {"tag_name": "v3.31.0"},
        )

        tool = CMakeTool()
        result = tool.latest_version(client)

        assert isinstance(result, Ok)
        assert result.value == "3.31.0"
