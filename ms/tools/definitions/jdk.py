"""Eclipse Temurin JDK tool definition.

Eclipse Temurin is the successor to AdoptOpenJDK and provides
high-quality OpenJDK builds for all platforms.

Website: https://adoptium.net/
API: https://api.adoptium.net/v3/
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ms.core.result import Err, Ok, Result
from ms.tools.api import adoptium_jdk_url
from ms.tools.base import Mode, Tool, ToolSpec
from ms.tools.http import HttpError

if TYPE_CHECKING:
    from pathlib import Path

    from ms.platform.detection import Arch, Platform
    from ms.tools.http import HttpClient

__all__ = ["JdkTool"]


# Platform mapping for Adoptium API
_ADOPTIUM_OS: dict[str, str] = {
    "linux": "linux",
    "macos": "mac",
    "windows": "windows",
}

_ADOPTIUM_ARCH: dict[str, str] = {
    "x64": "x64",
    "arm64": "aarch64",
}


class JdkTool(Tool):
    """Eclipse Temurin JDK - uses Adoptium API.

    JDK is special because:
    - Uses Adoptium API (not GitHub releases)
    - Requires JAVA_HOME environment variable
    - Binary is in bin/java under the install directory
    - Archives have a root directory (jdk-{version}/) to strip

    The JAVA_HOME setup is handled by the shell activation scripts,
    not by this tool directly.
    """

    spec = ToolSpec(
        id="jdk",
        name="Eclipse Temurin JDK",
        required_for=frozenset({Mode.ENDUSER, Mode.DEV}),
        version_args=("-version",),  # java -version
    )

    # Default JDK major version
    major_version: int = 21

    # Cache for download URL (set by latest_version)
    _cached_url: str | None = None
    _cached_version: str | None = None

    def _get_adoptium_os(self, platform: Platform) -> str | None:
        """Get Adoptium OS string."""
        return _ADOPTIUM_OS.get(str(platform).lower())

    def _get_adoptium_arch(self, arch: Arch) -> str | None:
        """Get Adoptium architecture string."""
        return _ADOPTIUM_ARCH.get(str(arch).lower())

    def latest_version(self, http: HttpClient) -> Result[str, HttpError]:
        """Fetch latest JDK version from Adoptium.

        This also caches the download URL for use by download_url().

        Note: We default to x64 linux for version resolution since
        all platforms get the same version.
        """
        result = adoptium_jdk_url(http, self.major_version, "linux", "x64")

        if isinstance(result, Err):
            return result

        url, version = result.value
        self._cached_url = url
        self._cached_version = version
        return Ok(version)

    def download_url(self, version: str, platform: Platform, arch: Arch) -> str:
        """Get download URL for specific version and platform.

        Since Adoptium URLs are complex and include checksums,
        we must call the API for each platform.
        """
        os_str = self._get_adoptium_os(platform) or "linux"
        arch_str = self._get_adoptium_arch(arch) or "x64"

        # Construct Adoptium binary URL
        # Format: https://api.adoptium.net/v3/binary/version/{release_name}/{os}/{arch}/jdk/hotspot/normal/eclipse
        # We use the release_name from version (e.g., "jdk-21.0.2+13")
        release_name = version if version.startswith("jdk-") else f"jdk-{version}"

        # URL-encode the release name (+ becomes %2B)
        encoded_release = release_name.replace("+", "%2B")

        return (
            f"https://api.adoptium.net/v3/binary/version/{encoded_release}"
            f"/{os_str}/{arch_str}/jdk/hotspot/normal/eclipse"
        )

    def strip_components(self) -> int:
        """JDK archives have a root directory to strip."""
        return 1

    def bin_path(self, tools_dir: Path, platform: Platform) -> Path | None:
        """JDK binary is in bin/java under the jdk/ directory."""
        return tools_dir / "jdk" / "bin" / platform.exe_name("java")

    def post_install(self, install_dir: Path, platform: Platform) -> None:
        """Make binaries executable on Unix."""
        if platform.is_unix:
            bin_dir = install_dir / "bin"
            if bin_dir.exists():
                for binary in bin_dir.iterdir():
                    if binary.is_file():
                        binary.chmod(0o755)

    def java_home(self, tools_dir: Path) -> Path:
        """Get JAVA_HOME path for this JDK installation.

        This is used by shell activation scripts to set JAVA_HOME.
        """
        return tools_dir / "jdk"
