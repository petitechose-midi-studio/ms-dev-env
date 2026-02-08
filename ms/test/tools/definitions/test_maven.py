"""Tests for MavenTool."""

import sys
from pathlib import Path

import pytest

from ms.core.result import Err, Ok
from ms.platform.detection import Arch, Platform
from ms.tools.base import Mode
from ms.tools.definitions.maven import MavenTool
from ms.tools.http import HttpError, MockHttpClient

# Sample Maven metadata XML
MAVEN_METADATA_XML = """<?xml version="1.0" encoding="UTF-8"?>
<metadata>
  <groupId>org.apache.maven</groupId>
  <artifactId>apache-maven</artifactId>
  <versioning>
    <latest>3.9.9</latest>
    <release>3.9.9</release>
    <versions>
      <version>3.0.4</version>
      <version>3.8.1</version>
      <version>3.8.6</version>
      <version>3.9.5</version>
      <version>3.9.6</version>
      <version>3.9.9</version>
      <version>4.0.0-alpha-7</version>
    </versions>
  </versioning>
</metadata>
"""


class TestMavenTool:
    """Tests for MavenTool."""

    def test_spec(self) -> None:
        """MavenTool has correct spec."""
        tool = MavenTool()

        assert tool.spec.id == "maven"
        assert tool.spec.name == "Apache Maven"
        assert tool.spec.required_for == frozenset({Mode.DEV, Mode.ENDUSER})

    def test_install_dir_name(self) -> None:
        """MavenTool installs to 'maven' directory."""
        tool = MavenTool()

        assert tool.install_dir_name() == "maven"

    def test_strip_components(self) -> None:
        """Maven archive has root directory to strip."""
        tool = MavenTool()

        assert tool.strip_components() == 1

    def test_major_prefix_default(self) -> None:
        """Default major prefix is 3.9."""
        tool = MavenTool()

        assert tool.major_prefix == "3.9"


class TestMavenToolLatestVersion:
    """Tests for MavenTool.latest_version()."""

    def test_success(self) -> None:
        """Fetch latest version from Maven Central."""
        client = MockHttpClient()
        client.set_text(
            "https://repo1.maven.org/maven2/org/apache/maven/apache-maven/maven-metadata.xml",
            MAVEN_METADATA_XML,
        )

        tool = MavenTool()
        result = tool.latest_version(client)

        assert isinstance(result, Ok)
        assert result.value == "3.9.9"

    def test_filters_by_major_prefix(self) -> None:
        """Version filtering respects major_prefix."""
        xml_38 = """<?xml version="1.0"?>
        <metadata>
          <versions>
            <version>3.8.1</version>
            <version>3.8.6</version>
            <version>3.9.1</version>
          </versions>
        </metadata>
        """
        client = MockHttpClient()
        client.set_text(
            "https://repo1.maven.org/maven2/org/apache/maven/apache-maven/maven-metadata.xml",
            xml_38,
        )

        tool = MavenTool()
        tool.major_prefix = "3.8"
        result = tool.latest_version(client)

        assert isinstance(result, Ok)
        assert result.value == "3.8.6"

    def test_error_no_versions(self) -> None:
        """Error when no versions in metadata."""
        xml = """<?xml version="1.0"?><metadata></metadata>"""
        client = MockHttpClient()
        client.set_text(
            "https://repo1.maven.org/maven2/org/apache/maven/apache-maven/maven-metadata.xml",
            xml,
        )

        tool = MavenTool()
        result = tool.latest_version(client)

        assert isinstance(result, Err)

    def test_error_network(self) -> None:
        """Error on network failure."""
        client = MockHttpClient()
        client.set_text(
            "https://repo1.maven.org/maven2/org/apache/maven/apache-maven/maven-metadata.xml",
            HttpError(url="...", status=500, message="Server error"),
        )

        tool = MavenTool()
        result = tool.latest_version(client)

        assert isinstance(result, Err)


class TestMavenToolDownloadUrl:
    """Tests for MavenTool.download_url()."""

    def test_linux_x64(self) -> None:
        """Download URL for Linux x64."""
        tool = MavenTool()

        url = tool.download_url("3.9.6", Platform.LINUX, Arch.X64)

        assert (
            url
            == "https://archive.apache.org/dist/maven/maven-3/3.9.6/binaries/apache-maven-3.9.6-bin.tar.gz"
        )

    def test_macos_arm64(self) -> None:
        """Download URL is same for macOS ARM64 (platform independent)."""
        tool = MavenTool()

        url = tool.download_url("3.9.6", Platform.MACOS, Arch.ARM64)

        assert (
            url
            == "https://archive.apache.org/dist/maven/maven-3/3.9.6/binaries/apache-maven-3.9.6-bin.tar.gz"
        )

    def test_windows_x64(self) -> None:
        """Download URL is same for Windows (platform independent)."""
        tool = MavenTool()

        url = tool.download_url("3.9.6", Platform.WINDOWS, Arch.X64)

        # Same tar.gz for Windows too (extracted differently)
        assert (
            url
            == "https://archive.apache.org/dist/maven/maven-3/3.9.6/binaries/apache-maven-3.9.6-bin.tar.gz"
        )


class TestMavenToolBinPath:
    """Tests for MavenTool.bin_path()."""

    def test_linux(self) -> None:
        """Binary path on Linux."""
        tool = MavenTool()

        path = tool.bin_path(Path("/tools"), Platform.LINUX)

        assert path == Path("/tools/maven/bin/mvn")

    def test_macos(self) -> None:
        """Binary path on macOS."""
        tool = MavenTool()

        path = tool.bin_path(Path("/tools"), Platform.MACOS)

        assert path == Path("/tools/maven/bin/mvn")

    def test_windows(self) -> None:
        """Binary path on Windows uses mvn.cmd."""
        tool = MavenTool()

        path = tool.bin_path(Path("/tools"), Platform.WINDOWS)

        assert path == Path("/tools/maven/bin/mvn.cmd")


class TestMavenToolInstallation:
    """Tests for MavenTool installation methods."""

    def test_is_installed_true(self, tmp_path: Path) -> None:
        """MavenTool is installed if mvn binary exists."""
        tool = MavenTool()

        # Create mvn binary
        bin_dir = tmp_path / "maven" / "bin"
        bin_dir.mkdir(parents=True)
        (bin_dir / "mvn").touch()

        assert tool.is_installed(tmp_path, Platform.LINUX) is True

    def test_is_installed_false(self, tmp_path: Path) -> None:
        """MavenTool is not installed if binary doesn't exist."""
        tool = MavenTool()

        assert tool.is_installed(tmp_path, Platform.LINUX) is False

    def test_is_installed_windows(self, tmp_path: Path) -> None:
        """MavenTool checks for mvn.cmd on Windows."""
        tool = MavenTool()

        # Create mvn.cmd
        bin_dir = tmp_path / "maven" / "bin"
        bin_dir.mkdir(parents=True)
        (bin_dir / "mvn.cmd").touch()

        assert tool.is_installed(tmp_path, Platform.WINDOWS) is True

    @pytest.mark.skipif(sys.platform == "win32", reason="chmod doesn't work on Windows")
    def test_post_install_unix(self, tmp_path: Path) -> None:
        """Post-install makes scripts executable on Unix."""
        tool = MavenTool()

        # Create bin directory with scripts
        bin_dir = tmp_path / "bin"
        bin_dir.mkdir()
        mvn = bin_dir / "mvn"
        mvnDebug = bin_dir / "mvnDebug"
        mvn.touch()
        mvnDebug.touch()
        mvn.chmod(0o644)
        mvnDebug.chmod(0o644)

        tool.post_install(tmp_path, Platform.LINUX)

        assert mvn.stat().st_mode & 0o111  # At least one execute bit
        assert mvnDebug.stat().st_mode & 0o111

    def test_post_install_windows(self, tmp_path: Path) -> None:
        """Post-install on Windows doesn't fail."""
        tool = MavenTool()

        bin_dir = tmp_path / "bin"
        bin_dir.mkdir()
        (bin_dir / "mvn.cmd").touch()

        # Should not raise
        tool.post_install(tmp_path, Platform.WINDOWS)


class TestMavenToolM2Home:
    """Tests for MavenTool.m2_home()."""

    def test_m2_home(self) -> None:
        """m2_home returns tools/maven path."""
        tool = MavenTool()

        path = tool.m2_home(Path("/tools"))

        assert path == Path("/tools/maven")
