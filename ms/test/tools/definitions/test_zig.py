"""Tests for ZigTool."""

import sys
from pathlib import Path

import pytest

from ms.core.result import Ok
from ms.platform.detection import Arch, Platform
from ms.tools.base import Mode
from ms.tools.definitions.zig import ZigTool
from ms.tools.http import MockHttpClient


# Sample Zig index.json response
ZIG_INDEX_RESPONSE = {
    "master": {"version": "0.14.0-dev"},
    "0.13.0": {
        "x86_64-linux": {
            "tarball": "https://ziglang.org/download/0.13.0/zig-linux-x86_64-0.13.0.tar.xz",
            "size": 12345678,
        },
        "aarch64-linux": {
            "tarball": "https://ziglang.org/download/0.13.0/zig-linux-aarch64-0.13.0.tar.xz",
            "size": 12345678,
        },
        "x86_64-macos": {
            "tarball": "https://ziglang.org/download/0.13.0/zig-macos-x86_64-0.13.0.tar.xz",
            "size": 12345678,
        },
        "aarch64-macos": {
            "tarball": "https://ziglang.org/download/0.13.0/zig-macos-aarch64-0.13.0.tar.xz",
            "size": 12345678,
        },
        "x86_64-windows": {
            "tarball": "https://ziglang.org/download/0.13.0/zig-windows-x86_64-0.13.0.zip",
            "size": 12345678,
        },
    },
    "0.12.0": {
        "x86_64-linux": {
            "tarball": "https://ziglang.org/download/0.12.0/zig-linux-x86_64-0.12.0.tar.xz",
        },
    },
}


class TestZigTool:
    """Tests for ZigTool."""

    def test_spec(self) -> None:
        """ZigTool has correct spec."""
        tool = ZigTool()

        assert tool.spec.id == "zig"
        assert tool.spec.name == "Zig"
        assert tool.spec.required_for == frozenset({Mode.DEV})

    def test_install_dir_name(self) -> None:
        """ZigTool installs to 'zig' directory."""
        tool = ZigTool()

        assert tool.install_dir_name() == "zig"

    def test_strip_components(self) -> None:
        """Zig archive has root directory to strip."""
        tool = ZigTool()

        assert tool.strip_components() == 1


class TestZigToolLatestVersion:
    """Tests for ZigTool.latest_version()."""

    def test_success(self) -> None:
        """Fetch latest version from ziglang.org."""
        client = MockHttpClient()
        client.set_json("https://ziglang.org/download/index.json", ZIG_INDEX_RESPONSE)

        tool = ZigTool()
        result = tool.latest_version(client)

        assert isinstance(result, Ok)
        assert result.value == "0.13.0"

    def test_caches_platform_urls(self) -> None:
        """latest_version caches platform URLs."""
        client = MockHttpClient()
        client.set_json("https://ziglang.org/download/index.json", ZIG_INDEX_RESPONSE)

        tool = ZigTool()
        tool.latest_version(client)

        # Check that platform URLs were cached
        assert tool._platform_urls is not None
        assert "x86_64-linux" in tool._platform_urls
        assert tool._cached_version == "0.13.0"


class TestZigToolDownloadUrl:
    """Tests for ZigTool.download_url()."""

    def test_with_cached_urls(self) -> None:
        """Use cached URLs from latest_version."""
        client = MockHttpClient()
        client.set_json("https://ziglang.org/download/index.json", ZIG_INDEX_RESPONSE)

        tool = ZigTool()
        tool.latest_version(client)

        url = tool.download_url("0.13.0", Platform.LINUX, Arch.X64)

        assert url == "https://ziglang.org/download/0.13.0/zig-linux-x86_64-0.13.0.tar.xz"

    def test_linux_arm64(self) -> None:
        """Download URL for Linux ARM64."""
        client = MockHttpClient()
        client.set_json("https://ziglang.org/download/index.json", ZIG_INDEX_RESPONSE)

        tool = ZigTool()
        tool.latest_version(client)

        url = tool.download_url("0.13.0", Platform.LINUX, Arch.ARM64)

        assert url == "https://ziglang.org/download/0.13.0/zig-linux-aarch64-0.13.0.tar.xz"

    def test_macos_arm64(self) -> None:
        """Download URL for macOS ARM64."""
        client = MockHttpClient()
        client.set_json("https://ziglang.org/download/index.json", ZIG_INDEX_RESPONSE)

        tool = ZigTool()
        tool.latest_version(client)

        url = tool.download_url("0.13.0", Platform.MACOS, Arch.ARM64)

        assert url == "https://ziglang.org/download/0.13.0/zig-macos-aarch64-0.13.0.tar.xz"

    def test_windows(self) -> None:
        """Download URL for Windows."""
        client = MockHttpClient()
        client.set_json("https://ziglang.org/download/index.json", ZIG_INDEX_RESPONSE)

        tool = ZigTool()
        tool.latest_version(client)

        url = tool.download_url("0.13.0", Platform.WINDOWS, Arch.X64)

        assert url == "https://ziglang.org/download/0.13.0/zig-windows-x86_64-0.13.0.zip"

    def test_fallback_without_cache(self) -> None:
        """Construct URL from pattern when no cache."""
        tool = ZigTool()

        # Without calling latest_version first
        url = tool.download_url("0.13.0", Platform.LINUX, Arch.X64)

        # Should use fallback pattern
        assert "0.13.0" in url
        assert "x86_64-linux" in url


class TestZigToolBinPath:
    """Tests for ZigTool.bin_path()."""

    def test_linux(self) -> None:
        """Binary path on Linux."""
        tool = ZigTool()

        path = tool.bin_path(Path("/tools"), Platform.LINUX)

        assert path == Path("/tools/zig/zig")

    def test_macos(self) -> None:
        """Binary path on macOS."""
        tool = ZigTool()

        path = tool.bin_path(Path("/tools"), Platform.MACOS)

        assert path == Path("/tools/zig/zig")

    def test_windows(self) -> None:
        """Binary path on Windows includes .exe."""
        tool = ZigTool()

        path = tool.bin_path(Path("/tools"), Platform.WINDOWS)

        assert path == Path("/tools/zig/zig.exe")


class TestZigToolInstallation:
    """Tests for ZigTool installation methods."""

    def test_is_installed_true(self, tmp_path: Path) -> None:
        """ZigTool is installed if binary exists."""
        tool = ZigTool()

        # Create zig binary
        zig_dir = tmp_path / "zig"
        zig_dir.mkdir()
        (zig_dir / "zig").touch()

        assert tool.is_installed(tmp_path, Platform.LINUX) is True

    def test_is_installed_false(self, tmp_path: Path) -> None:
        """ZigTool is not installed if binary doesn't exist."""
        tool = ZigTool()

        assert tool.is_installed(tmp_path, Platform.LINUX) is False

    @pytest.mark.skipif(sys.platform == "win32", reason="chmod doesn't work on Windows")
    def test_post_install_unix(self, tmp_path: Path) -> None:
        """Post-install makes zig executable on Unix."""
        tool = ZigTool()

        # Create zig binary
        zig = tmp_path / "zig"
        zig.touch()
        zig.chmod(0o644)

        tool.post_install(tmp_path, Platform.LINUX)

        mode = zig.stat().st_mode
        assert mode & 0o111  # At least one execute bit

    def test_post_install_windows(self, tmp_path: Path) -> None:
        """Post-install on Windows doesn't fail."""
        tool = ZigTool()

        zig = tmp_path / "zig.exe"
        zig.touch()

        # Should not raise
        tool.post_install(tmp_path, Platform.WINDOWS)
