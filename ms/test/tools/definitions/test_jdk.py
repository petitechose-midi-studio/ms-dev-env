"""Tests for JdkTool."""

import json
import sys
from pathlib import Path

import pytest

from ms.core.result import Err, Ok
from ms.platform.detection import Arch, Platform
from ms.tools.base import Mode
from ms.tools.definitions.jdk import JdkTool
from ms.tools.http import HttpError, MockHttpClient


# Sample Adoptium API response
ADOPTIUM_RESPONSE = [
    {
        "binary": {
            "package": {
                "link": "https://github.com/adoptium/temurin21-binaries/releases/download/jdk-21.0.2%2B13/OpenJDK21U-jdk_x64_linux_hotspot_21.0.2_13.tar.gz",
            },
        },
        "release_name": "jdk-21.0.2+13",
        "version": {
            "semver": "21.0.2+13",
        },
    }
]


class TestJdkTool:
    """Tests for JdkTool."""

    def test_spec(self) -> None:
        """JdkTool has correct spec."""
        tool = JdkTool()

        assert tool.spec.id == "jdk"
        assert tool.spec.name == "Eclipse Temurin JDK"
        assert tool.spec.required_for == frozenset({Mode.DEV, Mode.ENDUSER})
        assert tool.spec.version_args == ("-version",)

    def test_install_dir_name(self) -> None:
        """JdkTool installs to 'jdk' directory."""
        tool = JdkTool()

        assert tool.install_dir_name() == "jdk"

    def test_strip_components(self) -> None:
        """JDK archive has root directory to strip."""
        tool = JdkTool()

        assert tool.strip_components() == 1

    def test_major_version_default(self) -> None:
        """Default JDK major version is 21."""
        tool = JdkTool()

        assert tool.major_version == 21


class TestJdkToolLatestVersion:
    """Tests for JdkTool.latest_version()."""

    def test_success(self) -> None:
        """Fetch latest version from Adoptium."""
        client = MockHttpClient()
        client.set_text(
            "https://api.adoptium.net/v3/assets/latest/21/hotspot?architecture=x64&image_type=jdk&os=linux&vendor=eclipse",
            json.dumps(ADOPTIUM_RESPONSE),
        )

        tool = JdkTool()
        result = tool.latest_version(client)

        assert isinstance(result, Ok)
        assert result.value == "21.0.2+13"

    def test_returns_release_name_if_no_semver(self) -> None:
        """Use release_name if semver is not available."""
        response = [
            {
                "binary": {
                    "package": {
                        "link": "https://example.com/jdk.tar.gz",
                    },
                },
                "release_name": "jdk-21.0.2+13",
            }
        ]
        client = MockHttpClient()
        client.set_text(
            "https://api.adoptium.net/v3/assets/latest/21/hotspot?architecture=x64&image_type=jdk&os=linux&vendor=eclipse",
            json.dumps(response),
        )

        tool = JdkTool()
        result = tool.latest_version(client)

        assert isinstance(result, Ok)
        assert result.value == "jdk-21.0.2+13"

    def test_error_empty_response(self) -> None:
        """Error when Adoptium returns empty array."""
        client = MockHttpClient()
        client.set_text(
            "https://api.adoptium.net/v3/assets/latest/21/hotspot?architecture=x64&image_type=jdk&os=linux&vendor=eclipse",
            "[]",
        )

        tool = JdkTool()
        result = tool.latest_version(client)

        assert isinstance(result, Err)
        assert "No JDK releases found" in result.error.message

    def test_error_network(self) -> None:
        """Error on network failure."""
        client = MockHttpClient()
        client.set_text(
            "https://api.adoptium.net/v3/assets/latest/21/hotspot?architecture=x64&image_type=jdk&os=linux&vendor=eclipse",
            HttpError(url="...", status=500, message="Server error"),
        )

        tool = JdkTool()
        result = tool.latest_version(client)

        assert isinstance(result, Err)


class TestJdkToolDownloadUrl:
    """Tests for JdkTool.download_url()."""

    def test_linux_x64(self) -> None:
        """Download URL for Linux x64."""
        tool = JdkTool()

        url = tool.download_url("21.0.2+13", Platform.LINUX, Arch.X64)

        assert "api.adoptium.net" in url
        assert "linux" in url
        assert "x64" in url
        assert "21.0.2%2B13" in url  # + encoded as %2B

    def test_linux_arm64(self) -> None:
        """Download URL for Linux ARM64."""
        tool = JdkTool()

        url = tool.download_url("21.0.2+13", Platform.LINUX, Arch.ARM64)

        assert "aarch64" in url
        assert "linux" in url

    def test_macos_x64(self) -> None:
        """Download URL for macOS x64."""
        tool = JdkTool()

        url = tool.download_url("21.0.2+13", Platform.MACOS, Arch.X64)

        assert "mac" in url
        assert "x64" in url

    def test_macos_arm64(self) -> None:
        """Download URL for macOS ARM64."""
        tool = JdkTool()

        url = tool.download_url("21.0.2+13", Platform.MACOS, Arch.ARM64)

        assert "mac" in url
        assert "aarch64" in url

    def test_windows_x64(self) -> None:
        """Download URL for Windows x64."""
        tool = JdkTool()

        url = tool.download_url("21.0.2+13", Platform.WINDOWS, Arch.X64)

        assert "windows" in url
        assert "x64" in url

    def test_windows_arm64(self) -> None:
        """Download URL for Windows ARM64."""
        tool = JdkTool()

        url = tool.download_url("21.0.2+13", Platform.WINDOWS, Arch.ARM64)

        assert "windows" in url
        assert "aarch64" in url

    def test_version_with_jdk_prefix(self) -> None:
        """Version already with jdk- prefix is kept."""
        tool = JdkTool()

        url = tool.download_url("jdk-21.0.2+13", Platform.LINUX, Arch.X64)

        # Should not double the prefix
        assert "jdk-jdk-" not in url
        assert "jdk-21.0.2" in url


class TestJdkToolBinPath:
    """Tests for JdkTool.bin_path()."""

    def test_linux(self) -> None:
        """Binary path on Linux."""
        tool = JdkTool()

        path = tool.bin_path(Path("/tools"), Platform.LINUX)

        assert path == Path("/tools/jdk/bin/java")

    def test_macos(self) -> None:
        """Binary path on macOS."""
        tool = JdkTool()

        path = tool.bin_path(Path("/tools"), Platform.MACOS)

        assert path == Path("/tools/jdk/bin/java")

    def test_windows(self) -> None:
        """Binary path on Windows includes .exe."""
        tool = JdkTool()

        path = tool.bin_path(Path("/tools"), Platform.WINDOWS)

        assert path == Path("/tools/jdk/bin/java.exe")


class TestJdkToolInstallation:
    """Tests for JdkTool installation methods."""

    def test_is_installed_true(self, tmp_path: Path) -> None:
        """JdkTool is installed if java binary exists."""
        tool = JdkTool()

        # Create java binary
        bin_dir = tmp_path / "jdk" / "bin"
        bin_dir.mkdir(parents=True)
        (bin_dir / "java").touch()

        assert tool.is_installed(tmp_path, Platform.LINUX) is True

    def test_is_installed_false(self, tmp_path: Path) -> None:
        """JdkTool is not installed if binary doesn't exist."""
        tool = JdkTool()

        assert tool.is_installed(tmp_path, Platform.LINUX) is False

    @pytest.mark.skipif(sys.platform == "win32", reason="chmod doesn't work on Windows")
    def test_post_install_unix(self, tmp_path: Path) -> None:
        """Post-install makes all binaries executable on Unix."""
        tool = JdkTool()

        # Create bin directory with multiple binaries
        bin_dir = tmp_path / "bin"
        bin_dir.mkdir()
        java = bin_dir / "java"
        javac = bin_dir / "javac"
        java.touch()
        javac.touch()
        java.chmod(0o644)
        javac.chmod(0o644)

        tool.post_install(tmp_path, Platform.LINUX)

        assert java.stat().st_mode & 0o111  # At least one execute bit
        assert javac.stat().st_mode & 0o111

    def test_post_install_windows(self, tmp_path: Path) -> None:
        """Post-install on Windows doesn't fail."""
        tool = JdkTool()

        bin_dir = tmp_path / "bin"
        bin_dir.mkdir()
        (bin_dir / "java.exe").touch()

        # Should not raise
        tool.post_install(tmp_path, Platform.WINDOWS)


class TestJdkToolJavaHome:
    """Tests for JdkTool.java_home()."""

    def test_java_home(self) -> None:
        """java_home returns tools/jdk path."""
        tool = JdkTool()

        path = tool.java_home(Path("/tools"))

        assert path == Path("/tools/jdk")
