"""Eclipse Temurin JDK tool definition.

Eclipse Temurin is the successor to AdoptOpenJDK and provides
high-quality OpenJDK builds for all platforms.

Website: https://adoptium.net/
API: https://api.adoptium.net/v3/
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ms.core.result import Err, Ok, Result
from ms.platform.detection import Arch, Platform
from ms.tools.api import adoptium_jdk_url
from ms.tools.base import Mode, Tool, ToolSpec
from ms.tools.http import HttpError

if TYPE_CHECKING:
    from pathlib import Path

    from ms.tools.http import HttpClient

__all__ = ["JdkTool", "DEFAULT_JDK_MAJOR"]

# Default JDK major version (latest LTS)
DEFAULT_JDK_MAJOR = 25


# Platform mapping for Adoptium API
_ADOPTIUM_OS: dict[Platform, str] = {
    Platform.LINUX: "linux",
    Platform.MACOS: "mac",
    Platform.WINDOWS: "windows",
}

_ADOPTIUM_ARCH: dict[Arch, str] = {
    Arch.X64: "x64",
    Arch.ARM64: "aarch64",
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

    # JDK major version (configurable via toolchains.toml)
    major_version: int = DEFAULT_JDK_MAJOR

    def _get_adoptium_os(self, platform: Platform) -> str | None:
        """Get Adoptium OS string."""
        return _ADOPTIUM_OS.get(platform)

    def _get_adoptium_arch(self, arch: Arch) -> str | None:
        """Get Adoptium architecture string."""
        return _ADOPTIUM_ARCH.get(arch)

    def latest_version(self, http: HttpClient) -> Result[str, HttpError]:
        """Fetch latest JDK version from Adoptium.

        Note: We default to x64 linux for version resolution since
        all platforms get the same version.
        """
        result = adoptium_jdk_url(http, self.major_version, "linux", "x64")

        if isinstance(result, Err):
            return result

        _, version = result.value
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

    def _java_home_dir(self, tools_dir: Path) -> Path:
        """Resolve JAVA_HOME for the extracted JDK layout.

        On macOS, Adoptium JDK archives typically contain a .jdk bundle layout:
        jdk/Contents/Home/bin/java

        On Linux/Windows, the expected layout is:
        jdk/bin/java
        """
        macos_home = tools_dir / "jdk" / "Contents" / "Home"
        if macos_home.is_dir():
            return macos_home
        return tools_dir / "jdk"

    def bin_path(self, tools_dir: Path, platform: Platform) -> Path | None:
        """JDK binary is in bin/java under the jdk/ directory."""
        if platform.is_macos:
            return tools_dir / "jdk" / "Contents" / "Home" / "bin" / platform.exe_name("java")
        return tools_dir / "jdk" / "bin" / platform.exe_name("java")

    def post_install(self, install_dir: Path, platform: Platform) -> None:
        """Make binaries executable on Unix."""
        if platform.is_unix:
            # JDK layout differs on macOS (Contents/Home/bin).
            bin_dir = install_dir / "bin"
            if platform.is_macos:
                macos_bin = install_dir / "Contents" / "Home" / "bin"
                if macos_bin.is_dir():
                    bin_dir = macos_bin
            if bin_dir.exists():
                for binary in bin_dir.iterdir():
                    if binary.is_file():
                        binary.chmod(0o755)

    def java_home(self, tools_dir: Path) -> Path:
        """Get JAVA_HOME path for this JDK installation.

        This is used by shell activation scripts to set JAVA_HOME.
        """
        return self._java_home_dir(tools_dir)
