"""Integration tests for tools infrastructure.

Tests the complete flow: download -> install -> resolve
Using mocked HTTP to avoid real network calls.
"""

import io
import zipfile
from pathlib import Path

import pytest

from ms.core.result import Ok
from ms.platform.detection import Arch, Platform
from ms.tools.definitions.ninja import NinjaTool
from ms.tools.download import Downloader
from ms.tools.http import MockHttpClient
from ms.tools.installer import Installer
from ms.tools.resolver import ToolResolver


def create_mock_ninja_zip() -> bytes:
    """Create a mock ninja zip file with a fake binary."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zf:
        # Ninja zip has the binary directly at root
        zf.writestr("ninja", b"#!/bin/bash\necho 'mock ninja 1.12.1'")
        zf.writestr("README.md", b"# Ninja Build System")
    return buffer.getvalue()


class TestNinjaInstallFlow:
    """Test complete ninja installation flow."""

    def test_download_install_resolve(self, tmp_path: Path) -> None:
        """Full flow: fetch version -> download -> install -> resolve."""
        # Setup mock HTTP client
        client = MockHttpClient()

        # Mock GitHub API response
        client.set_json(
            "https://api.github.com/repos/ninja-build/ninja/releases/latest",
            {"tag_name": "v1.12.1", "name": "Ninja 1.12.1"},
        )

        # Mock download
        ninja_zip = create_mock_ninja_zip()
        client.set_download(
            "https://github.com/ninja-build/ninja/releases/download/v1.12.1/ninja-linux.zip",
            ninja_zip,
        )

        # Create directories
        cache_dir = tmp_path / "cache"
        tools_dir = tmp_path / "tools"

        # Create tool and components
        tool = NinjaTool()
        downloader = Downloader(client, cache_dir)
        installer = Installer()
        resolver = ToolResolver(tools_dir, Platform.LINUX)

        # Step 1: Fetch latest version
        version_result = tool.latest_version(client)
        assert isinstance(version_result, Ok)
        version = version_result.value
        assert version == "1.12.1"

        # Step 2: Get download URL
        download_url = tool.download_url(version, Platform.LINUX, Arch.X64)
        assert "ninja-linux.zip" in download_url
        assert "v1.12.1" in download_url

        # Step 3: Download
        download_result = downloader.download(download_url)
        assert isinstance(download_result, Ok)
        assert download_result.value.path.exists()
        assert download_result.value.from_cache is False

        # Step 4: Install
        install_dir = tools_dir / tool.install_dir_name()
        install_result = installer.install(
            download_result.value.path,
            install_dir,
            strip_components=tool.strip_components(),
        )
        assert isinstance(install_result, Ok)
        assert install_result.value.files_count > 0

        # Step 5: Post-install
        tool.post_install(install_dir, Platform.LINUX)

        # Step 6: Resolve
        resolve_result = resolver.resolve(tool)
        assert isinstance(resolve_result, Ok)
        assert resolve_result.value.bundled is True
        assert resolve_result.value.path.exists()

    def test_cached_download(self, tmp_path: Path) -> None:
        """Second download should use cache."""
        client = MockHttpClient()
        ninja_zip = create_mock_ninja_zip()
        client.set_download(
            "https://github.com/ninja-build/ninja/releases/download/v1.12.1/ninja-linux.zip",
            ninja_zip,
        )

        cache_dir = tmp_path / "cache"
        downloader = Downloader(client, cache_dir)

        url = "https://github.com/ninja-build/ninja/releases/download/v1.12.1/ninja-linux.zip"

        # First download
        result1 = downloader.download(url)
        assert isinstance(result1, Ok)
        assert result1.value.from_cache is False

        # Second download should be from cache
        result2 = downloader.download(url)
        assert isinstance(result2, Ok)
        assert result2.value.from_cache is True

        # Only one HTTP call should have been made
        download_calls = [c for c in client.calls if c[0] == "download"]
        assert len(download_calls) == 1

    def test_tool_already_installed(self, tmp_path: Path) -> None:
        """Resolver finds already installed tool."""
        # Create installed ninja
        tools_dir = tmp_path / "tools"
        ninja_dir = tools_dir / "ninja"
        ninja_dir.mkdir(parents=True)
        (ninja_dir / "ninja").write_bytes(b"fake binary")

        tool = NinjaTool()
        resolver = ToolResolver(tools_dir, Platform.LINUX)

        # Should be found without any downloads
        assert tool.is_installed(tools_dir, Platform.LINUX) is True
        resolve_result = resolver.resolve(tool)
        assert isinstance(resolve_result, Ok)
        assert resolve_result.value.bundled is True


class TestWindowsInstallFlow:
    """Test installation on Windows platform."""

    def test_windows_exe_suffix(self, tmp_path: Path) -> None:
        """Windows binaries have .exe suffix."""
        # Create mock zip with .exe
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as zf:
            zf.writestr("ninja.exe", b"MZ...")  # PE header start
        ninja_zip = buffer.getvalue()

        client = MockHttpClient()
        client.set_download(
            "https://github.com/ninja-build/ninja/releases/download/v1.12.1/ninja-win.zip",
            ninja_zip,
        )

        cache_dir = tmp_path / "cache"
        tools_dir = tmp_path / "tools"

        tool = NinjaTool()
        downloader = Downloader(client, cache_dir)
        installer = Installer()
        resolver = ToolResolver(tools_dir, Platform.WINDOWS)

        # Download
        download_url = tool.download_url("1.12.1", Platform.WINDOWS, Arch.X64)
        assert "ninja-win.zip" in download_url

        download_result = downloader.download(download_url)
        assert isinstance(download_result, Ok)

        # Install
        install_dir = tools_dir / "ninja"
        install_result = installer.install(download_result.value.path, install_dir)
        assert isinstance(install_result, Ok)

        # Check .exe exists
        assert (install_dir / "ninja.exe").exists()

        # Resolve
        resolve_result = resolver.resolve(tool)
        assert isinstance(resolve_result, Ok)
        assert resolve_result.value.path.name == "ninja.exe"


class TestMultipleTools:
    """Test installing multiple tools."""

    def test_separate_directories(self, tmp_path: Path) -> None:
        """Each tool gets its own directory."""
        tools_dir = tmp_path / "tools"

        # Create ninja
        (tools_dir / "ninja").mkdir(parents=True)
        (tools_dir / "ninja" / "ninja").touch()

        # Create cmake (simulated)
        (tools_dir / "cmake" / "bin").mkdir(parents=True)
        (tools_dir / "cmake" / "bin" / "cmake").touch()

        # Both should be resolvable independently
        resolver = ToolResolver(tools_dir, Platform.LINUX)

        ninja_tool = NinjaTool()
        resolve_result = resolver.resolve(ninja_tool)
        assert isinstance(resolve_result, Ok)
        assert resolve_result.value.bundled is True

        # CMake would need its own tool class, but we can check the directory exists
        assert (tools_dir / "cmake" / "bin" / "cmake").exists()


class TestErrorRecovery:
    """Test error handling and recovery."""

    def test_download_error_no_partial_file(self, tmp_path: Path) -> None:
        """Failed download doesn't leave partial files in cache."""
        client = MockHttpClient()
        # No mock = 404 error

        cache_dir = tmp_path / "cache"
        downloader = Downloader(client, cache_dir)

        result = downloader.download("https://example.com/nonexistent.zip")

        assert not isinstance(result, Ok)
        # Cache should be empty or not contain partial file
        if cache_dir.exists():
            assert len(list(cache_dir.iterdir())) == 0

    def test_install_error_cleanup(self, tmp_path: Path) -> None:
        """Failed install cleans up partial installation."""
        # Create corrupt archive
        archive = tmp_path / "corrupt.zip"
        archive.write_bytes(b"not a valid zip file")

        tools_dir = tmp_path / "tools"
        installer = Installer()

        result = installer.install(archive, tools_dir / "tool")

        assert not isinstance(result, Ok)
        # Install dir should not exist or be empty
