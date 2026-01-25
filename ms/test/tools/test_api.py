"""Tests for tools/api.py - External API functions."""

import pytest

from ms.core.result import Err, Ok
from ms.tools.api import (
    adoptium_jdk_url,
    github_latest_release,
    maven_latest_version,
    zig_latest_stable,
)
from ms.tools.http import HttpError, MockHttpClient


# =============================================================================
# github_latest_release tests
# =============================================================================


class TestGithubLatestRelease:
    """Tests for github_latest_release()."""

    def test_success_with_v_prefix(self) -> None:
        """Parse release with v-prefixed tag."""
        client = MockHttpClient()
        client.set_json(
            "https://api.github.com/repos/ninja-build/ninja/releases/latest",
            {"tag_name": "v1.12.1", "name": "Ninja 1.12.1"},
        )

        result = github_latest_release(client, "ninja-build/ninja")

        assert isinstance(result, Ok)
        assert result.value == "1.12.1"

    def test_success_without_v_prefix(self) -> None:
        """Parse release without v-prefixed tag."""
        client = MockHttpClient()
        client.set_json(
            "https://api.github.com/repos/some/repo/releases/latest",
            {"tag_name": "2.0.0", "name": "Release 2.0.0"},
        )

        result = github_latest_release(client, "some/repo")

        assert isinstance(result, Ok)
        assert result.value == "2.0.0"

    def test_network_error(self) -> None:
        """Handle network error."""
        client = MockHttpClient()
        # No response set = 404

        result = github_latest_release(client, "nonexistent/repo")

        assert isinstance(result, Err)
        assert result.error.status == 404

    def test_missing_tag_name(self) -> None:
        """Handle response without tag_name."""
        client = MockHttpClient()
        client.set_json(
            "https://api.github.com/repos/bad/repo/releases/latest",
            {"name": "Some Release"},  # Missing tag_name
        )

        result = github_latest_release(client, "bad/repo")

        assert isinstance(result, Err)
        assert "tag_name" in result.error.message

    def test_api_error_response(self) -> None:
        """Handle API error response."""
        client = MockHttpClient()
        client.set_json(
            "https://api.github.com/repos/private/repo/releases/latest",
            HttpError(
                url="https://api.github.com/repos/private/repo/releases/latest",
                status=403,
                message="API rate limit exceeded",
            ),
        )

        result = github_latest_release(client, "private/repo")

        assert isinstance(result, Err)
        assert result.error.status == 403

    def test_tracks_api_call(self) -> None:
        """Verify correct API URL is called."""
        client = MockHttpClient()
        client.set_json(
            "https://api.github.com/repos/Kitware/CMake/releases/latest",
            {"tag_name": "v3.28.0"},
        )

        github_latest_release(client, "Kitware/CMake")

        assert (
            "get_json",
            "https://api.github.com/repos/Kitware/CMake/releases/latest",
        ) in client.calls


# =============================================================================
# adoptium_jdk_url tests
# =============================================================================


class TestAdoptiumJdkUrl:
    """Tests for adoptium_jdk_url()."""

    @pytest.fixture
    def mock_adoptium_response(self) -> str:
        """Sample Adoptium API response."""
        return """[
            {
                "binary": {
                    "package": {
                        "link": "https://github.com/adoptium/temurin21-binaries/releases/download/jdk-21.0.2%2B13/OpenJDK21U-jdk_x64_linux_hotspot_21.0.2_13.tar.gz"
                    }
                },
                "release_name": "jdk-21.0.2+13",
                "version": {
                    "semver": "21.0.2+13"
                }
            }
        ]"""

    def test_success(self, mock_adoptium_response: str) -> None:
        """Parse successful Adoptium response."""
        client = MockHttpClient()
        url = "https://api.adoptium.net/v3/assets/latest/21/hotspot?architecture=x64&image_type=jdk&os=linux&vendor=eclipse"
        client.set_text(url, mock_adoptium_response)

        result = adoptium_jdk_url(client, 21, "linux", "x64")

        assert isinstance(result, Ok)
        download_url, version = result.value
        assert "OpenJDK21U-jdk_x64_linux" in download_url
        assert version == "21.0.2+13"

    def test_mac_platform(self) -> None:
        """Fetch JDK for macOS."""
        client = MockHttpClient()
        response = """[{
            "binary": {"package": {"link": "https://example.com/jdk_mac.tar.gz"}},
            "release_name": "jdk-21.0.1+12",
            "version": {"semver": "21.0.1+12"}
        }]"""
        url = "https://api.adoptium.net/v3/assets/latest/21/hotspot?architecture=aarch64&image_type=jdk&os=mac&vendor=eclipse"
        client.set_text(url, response)

        result = adoptium_jdk_url(client, 21, "mac", "aarch64")

        assert isinstance(result, Ok)
        assert "mac" in result.value[0]

    def test_empty_response(self) -> None:
        """Handle empty releases array."""
        client = MockHttpClient()
        url = "https://api.adoptium.net/v3/assets/latest/99/hotspot?architecture=x64&image_type=jdk&os=linux&vendor=eclipse"
        client.set_text(url, "[]")

        result = adoptium_jdk_url(client, 99, "linux", "x64")

        assert isinstance(result, Err)
        assert "No JDK releases" in result.error.message

    def test_network_error(self) -> None:
        """Handle network error."""
        client = MockHttpClient()
        # No response set = 404

        result = adoptium_jdk_url(client, 21, "linux", "x64")

        assert isinstance(result, Err)

    def test_missing_binary(self) -> None:
        """Handle response without binary field."""
        client = MockHttpClient()
        url = "https://api.adoptium.net/v3/assets/latest/21/hotspot?architecture=x64&image_type=jdk&os=linux&vendor=eclipse"
        client.set_text(url, '[{"release_name": "jdk-21"}]')

        result = adoptium_jdk_url(client, 21, "linux", "x64")

        assert isinstance(result, Err)
        assert "binary" in result.error.message.lower()


# =============================================================================
# zig_latest_stable tests
# =============================================================================


class TestZigLatestStable:
    """Tests for zig_latest_stable()."""

    @pytest.fixture
    def mock_zig_index(self) -> dict[str, object]:
        """Sample Zig download index."""
        return {
            "master": {
                "version": "0.14.0-dev.1234+abc",
                "x86_64-linux": {
                    "tarball": "https://ziglang.org/builds/zig-linux-x86_64-0.14.0-dev.tar.xz"
                },
            },
            "0.13.0": {
                "x86_64-linux": {
                    "tarball": "https://ziglang.org/download/0.13.0/zig-linux-x86_64-0.13.0.tar.xz"
                },
                "x86_64-macos": {
                    "tarball": "https://ziglang.org/download/0.13.0/zig-macos-x86_64-0.13.0.tar.xz"
                },
                "x86_64-windows": {
                    "tarball": "https://ziglang.org/download/0.13.0/zig-windows-x86_64-0.13.0.zip"
                },
                "aarch64-linux": {
                    "tarball": "https://ziglang.org/download/0.13.0/zig-linux-aarch64-0.13.0.tar.xz"
                },
                "aarch64-macos": {
                    "tarball": "https://ziglang.org/download/0.13.0/zig-macos-aarch64-0.13.0.tar.xz"
                },
            },
            "0.12.0": {
                "x86_64-linux": {
                    "tarball": "https://ziglang.org/download/0.12.0/zig-linux-x86_64-0.12.0.tar.xz"
                },
            },
        }

    def test_success(self, mock_zig_index: dict[str, object]) -> None:
        """Fetch latest stable version."""
        client = MockHttpClient()
        client.set_json("https://ziglang.org/download/index.json", mock_zig_index)  # type: ignore[arg-type]

        result = zig_latest_stable(client)

        assert isinstance(result, Ok)
        version, urls = result.value
        assert version == "0.13.0"  # Latest stable, not master
        assert "x86_64-linux" in urls

    def test_excludes_master(self, mock_zig_index: dict[str, object]) -> None:
        """Master branch is excluded from stable versions."""
        client = MockHttpClient()
        client.set_json("https://ziglang.org/download/index.json", mock_zig_index)  # type: ignore[arg-type]

        result = zig_latest_stable(client)

        assert isinstance(result, Ok)
        version, _ = result.value
        assert "dev" not in version
        assert "master" != version

    def test_platform_urls(self, mock_zig_index: dict[str, object]) -> None:
        """Platform URLs are returned correctly."""
        client = MockHttpClient()
        client.set_json("https://ziglang.org/download/index.json", mock_zig_index)  # type: ignore[arg-type]

        result = zig_latest_stable(client)

        assert isinstance(result, Ok)
        _, urls = result.value
        assert "x86_64-linux" in urls
        assert "x86_64-macos" in urls
        assert "x86_64-windows" in urls
        assert "aarch64-linux" in urls
        assert "aarch64-macos" in urls

    def test_network_error(self) -> None:
        """Handle network error."""
        client = MockHttpClient()

        result = zig_latest_stable(client)

        assert isinstance(result, Err)

    def test_no_stable_versions(self) -> None:
        """Handle index with only master."""
        client = MockHttpClient()
        client.set_json(
            "https://ziglang.org/download/index.json",
            {"master": {"version": "0.14.0-dev"}},
        )

        result = zig_latest_stable(client)

        assert isinstance(result, Err)
        assert "No stable versions" in result.error.message


# =============================================================================
# maven_latest_version tests
# =============================================================================


class TestMavenLatestVersion:
    """Tests for maven_latest_version()."""

    @pytest.fixture
    def mock_maven_metadata(self) -> str:
        """Sample Maven metadata XML."""
        return """<?xml version="1.0" encoding="UTF-8"?>
<metadata>
  <groupId>org.apache.maven</groupId>
  <artifactId>apache-maven</artifactId>
  <versioning>
    <latest>3.9.6</latest>
    <release>3.9.6</release>
    <versions>
      <version>3.0.5</version>
      <version>3.6.3</version>
      <version>3.8.8</version>
      <version>3.9.0</version>
      <version>3.9.5</version>
      <version>3.9.6</version>
      <version>4.0.0-alpha-8</version>
    </versions>
    <lastUpdated>20240115120000</lastUpdated>
  </versioning>
</metadata>"""

    def test_success(self, mock_maven_metadata: str) -> None:
        """Fetch latest Maven version."""
        client = MockHttpClient()
        client.set_text(
            "https://repo1.maven.org/maven2/org/apache/maven/apache-maven/maven-metadata.xml",
            mock_maven_metadata,
        )

        result = maven_latest_version(client)

        assert isinstance(result, Ok)
        assert result.value == "3.9.6"

    def test_custom_major_prefix(self, mock_maven_metadata: str) -> None:
        """Filter by custom major prefix."""
        client = MockHttpClient()
        client.set_text(
            "https://repo1.maven.org/maven2/org/apache/maven/apache-maven/maven-metadata.xml",
            mock_maven_metadata,
        )

        result = maven_latest_version(client, major_prefix="3.8")

        assert isinstance(result, Ok)
        assert result.value == "3.8.8"

    def test_fallback_to_latest(self, mock_maven_metadata: str) -> None:
        """Fallback to latest if prefix not found."""
        client = MockHttpClient()
        client.set_text(
            "https://repo1.maven.org/maven2/org/apache/maven/apache-maven/maven-metadata.xml",
            mock_maven_metadata,
        )

        result = maven_latest_version(client, major_prefix="5.0")  # Doesn't exist

        assert isinstance(result, Ok)
        # Should return highest version overall (alpha excluded due to parsing)
        assert result.value in ("3.9.6", "4.0.0-alpha-8")

    def test_network_error(self) -> None:
        """Handle network error."""
        client = MockHttpClient()

        result = maven_latest_version(client)

        assert isinstance(result, Err)

    def test_empty_metadata(self) -> None:
        """Handle metadata with no versions."""
        client = MockHttpClient()
        client.set_text(
            "https://repo1.maven.org/maven2/org/apache/maven/apache-maven/maven-metadata.xml",
            "<metadata><versioning><versions></versions></versioning></metadata>",
        )

        result = maven_latest_version(client)

        assert isinstance(result, Err)
        assert "No versions" in result.error.message


# =============================================================================
# Integration tests
# =============================================================================


@pytest.mark.network
class TestApiIntegration:
    """Integration tests with real network calls.

    Run with: pytest -m network
    """

    def test_github_ninja(self) -> None:
        """Real GitHub API call for Ninja."""
        from ms.tools.http import RealHttpClient

        client = RealHttpClient()
        result = github_latest_release(client, "ninja-build/ninja")

        assert isinstance(result, Ok)
        # Version should be like "1.12.1"
        assert result.value[0].isdigit()

    def test_zig_latest(self) -> None:
        """Real Zig download index."""
        from ms.tools.http import RealHttpClient

        client = RealHttpClient()
        result = zig_latest_stable(client)

        assert isinstance(result, Ok)
        version, urls = result.value
        assert version[0].isdigit()
        assert "x86_64-linux" in urls

    def test_maven_latest(self) -> None:
        """Real Maven Central metadata."""
        from ms.tools.http import RealHttpClient

        client = RealHttpClient()
        result = maven_latest_version(client)

        assert isinstance(result, Ok)
        assert result.value.startswith("3.")
