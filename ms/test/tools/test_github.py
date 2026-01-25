"""Tests for tools/github.py - GitHubTool base class."""

import sys
from pathlib import Path

import pytest

from ms.core.result import Err, Ok
from ms.platform.detection import Arch, Platform
from ms.tools.base import Mode, ToolSpec
from ms.tools.github import GitHubTool
from ms.tools.http import HttpError, MockHttpClient


# =============================================================================
# Concrete implementation for testing
# =============================================================================


class SampleTool(GitHubTool):
    """Concrete GitHubTool for testing."""

    spec = ToolSpec(
        id="sampletool",
        name="Sample Tool",
        required_for=frozenset({Mode.DEV}),
    )
    repo = "test-org/sample-tool"

    def asset_name(self, version: str, platform: Platform, arch: Arch) -> str:
        """Simple asset naming."""
        match platform:
            case Platform.LINUX:
                suffix = "-aarch64" if arch == Arch.ARM64 else ""
                return f"sampletool-linux{suffix}.tar.gz"
            case Platform.MACOS:
                suffix = "-arm64" if arch == Arch.ARM64 else "-x64"
                return f"sampletool-macos{suffix}.zip"
            case Platform.WINDOWS:
                return "sampletool-win64.zip"
            case _:
                return "sampletool.tar.gz"


class SampleNestedTool(GitHubTool):
    """Tool with nested directory structure in archive."""

    spec = ToolSpec(
        id="nested",
        name="Nested Tool",
        required_for=frozenset({Mode.DEV}),
    )
    repo = "test-org/nested-tool"

    def asset_name(self, version: str, platform: Platform, arch: Arch) -> str:
        return f"nested-{version}.tar.gz"

    def strip_components(self) -> int:
        """Archive has nested-1.0.0/ prefix to strip."""
        return 1

    def bin_path(self, tools_dir: Path, platform: Platform) -> Path | None:
        """Binary is in bin/ subdirectory."""
        return tools_dir / "nested" / "bin" / platform.exe_name("nested")


# =============================================================================
# Tests
# =============================================================================


class TestGitHubTool:
    """Tests for GitHubTool base class."""

    def test_latest_version_success(self) -> None:
        """Fetch latest version from GitHub."""
        client = MockHttpClient()
        client.set_json(
            "https://api.github.com/repos/test-org/sample-tool/releases/latest",
            {"tag_name": "v1.2.3"},
        )

        tool = SampleTool()
        result = tool.latest_version(client)

        assert isinstance(result, Ok)
        assert result.value == "1.2.3"

    def test_latest_version_error(self) -> None:
        """Handle GitHub API error."""
        client = MockHttpClient()
        # No response = 404

        tool = SampleTool()
        result = tool.latest_version(client)

        assert isinstance(result, Err)
        assert result.error.status == 404

    def test_download_url_linux_x64(self) -> None:
        """Generate download URL for Linux x64."""
        tool = SampleTool()

        url = tool.download_url("1.2.3", Platform.LINUX, Arch.X64)

        assert (
            url
            == "https://github.com/test-org/sample-tool/releases/download/v1.2.3/sampletool-linux.tar.gz"
        )

    def test_download_url_linux_arm64(self) -> None:
        """Generate download URL for Linux ARM64."""
        tool = SampleTool()

        url = tool.download_url("1.2.3", Platform.LINUX, Arch.ARM64)

        assert (
            url
            == "https://github.com/test-org/sample-tool/releases/download/v1.2.3/sampletool-linux-aarch64.tar.gz"
        )

    def test_download_url_macos_x64(self) -> None:
        """Generate download URL for macOS x64."""
        tool = SampleTool()

        url = tool.download_url("2.0.0", Platform.MACOS, Arch.X64)

        assert (
            url
            == "https://github.com/test-org/sample-tool/releases/download/v2.0.0/sampletool-macos-x64.zip"
        )

    def test_download_url_macos_arm64(self) -> None:
        """Generate download URL for macOS ARM64."""
        tool = SampleTool()

        url = tool.download_url("2.0.0", Platform.MACOS, Arch.ARM64)

        assert (
            url
            == "https://github.com/test-org/sample-tool/releases/download/v2.0.0/sampletool-macos-arm64.zip"
        )

    def test_download_url_windows(self) -> None:
        """Generate download URL for Windows."""
        tool = SampleTool()

        url = tool.download_url("1.0.0", Platform.WINDOWS, Arch.X64)

        assert (
            url
            == "https://github.com/test-org/sample-tool/releases/download/v1.0.0/sampletool-win64.zip"
        )

    def test_install_dir_name_default(self) -> None:
        """Default install directory is tool id."""
        tool = SampleTool()

        assert tool.install_dir_name() == "sampletool"

    def test_strip_components_default(self) -> None:
        """Default strip_components is 0."""
        tool = SampleTool()

        assert tool.strip_components() == 0

    def test_strip_components_nested(self) -> None:
        """Nested tool has strip_components = 1."""
        tool = SampleNestedTool()

        assert tool.strip_components() == 1

    def test_bin_path_linux(self) -> None:
        """Binary path on Linux."""
        tool = SampleTool()

        path = tool.bin_path(Path("/tools"), Platform.LINUX)

        assert path == Path("/tools/sampletool/sampletool")

    def test_bin_path_windows(self) -> None:
        """Binary path on Windows includes .exe."""
        tool = SampleTool()

        path = tool.bin_path(Path("/tools"), Platform.WINDOWS)

        assert path == Path("/tools/sampletool/sampletool.exe")

    def test_bin_path_nested(self) -> None:
        """Nested tool has custom bin path."""
        tool = SampleNestedTool()

        path = tool.bin_path(Path("/tools"), Platform.LINUX)

        assert path == Path("/tools/nested/bin/nested")

    def test_is_installed_true(self, tmp_path: Path) -> None:
        """Tool is installed if binary exists."""
        tool = SampleTool()

        # Create binary
        binary = tmp_path / "sampletool" / "sampletool"
        binary.parent.mkdir(parents=True)
        binary.touch()

        assert tool.is_installed(tmp_path, Platform.LINUX) is True

    def test_is_installed_false(self, tmp_path: Path) -> None:
        """Tool is not installed if binary doesn't exist."""
        tool = SampleTool()

        assert tool.is_installed(tmp_path, Platform.LINUX) is False

    @pytest.mark.skipif(sys.platform == "win32", reason="chmod doesn't work on Windows")
    def test_post_install_unix(self, tmp_path: Path) -> None:
        """Post-install makes binary executable on Unix."""
        tool = SampleTool()

        # Create binary without executable permission
        install_dir = tmp_path / "sampletool"
        install_dir.mkdir()
        binary = install_dir / "sampletool"
        binary.touch()
        binary.chmod(0o644)

        tool.post_install(install_dir, Platform.LINUX)

        # Check executable bit is set
        mode = binary.stat().st_mode
        assert mode & 0o111  # At least one execute bit

    def test_post_install_windows(self, tmp_path: Path) -> None:
        """Post-install on Windows doesn't change permissions."""
        tool = SampleTool()

        # Create binary
        install_dir = tmp_path / "sampletool"
        install_dir.mkdir()
        binary = install_dir / "sampletool.exe"
        binary.touch()

        # Should not raise
        tool.post_install(install_dir, Platform.WINDOWS)

    def test_spec_accessible(self) -> None:
        """Tool spec is accessible."""
        tool = SampleTool()

        assert tool.spec.id == "sampletool"
        assert tool.spec.name == "Sample Tool"
        assert Mode.DEV in tool.spec.required_for


class TestGitHubToolAPIUsage:
    """Tests for GitHubTool API usage patterns."""

    def test_uses_correct_api_url(self) -> None:
        """Tool uses correct GitHub API URL."""
        client = MockHttpClient()
        client.set_json(
            "https://api.github.com/repos/test-org/sample-tool/releases/latest",
            {"tag_name": "v1.0.0"},
        )

        tool = SampleTool()
        tool.latest_version(client)

        # Verify API was called
        assert len(client.calls) == 1
        assert client.calls[0] == (
            "get_json",
            "https://api.github.com/repos/test-org/sample-tool/releases/latest",
        )

    def test_strips_v_prefix(self) -> None:
        """Version returned without 'v' prefix."""
        client = MockHttpClient()
        client.set_json(
            "https://api.github.com/repos/test-org/sample-tool/releases/latest",
            {"tag_name": "v2.0.0-beta.1"},
        )

        tool = SampleTool()
        result = tool.latest_version(client)

        assert isinstance(result, Ok)
        assert result.value == "2.0.0-beta.1"

    def test_handles_rate_limit(self) -> None:
        """Handle GitHub rate limit error."""
        client = MockHttpClient()
        client.set_json(
            "https://api.github.com/repos/test-org/sample-tool/releases/latest",
            HttpError(
                url="https://api.github.com/repos/test-org/sample-tool/releases/latest",
                status=403,
                message="API rate limit exceeded",
            ),
        )

        tool = SampleTool()
        result = tool.latest_version(client)

        assert isinstance(result, Err)
        assert result.error.status == 403
