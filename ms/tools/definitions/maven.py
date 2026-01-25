"""Apache Maven tool definition.

Apache Maven is a software project management and comprehension tool.
It's used for building Java projects including the Bitwig extension.

Website: https://maven.apache.org/
Download: https://maven.apache.org/download.cgi
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ms.core.result import Result
from ms.tools.api import maven_latest_version
from ms.tools.base import Mode, Tool, ToolSpec
from ms.tools.http import HttpError

if TYPE_CHECKING:
    from pathlib import Path

    from ms.platform.detection import Arch, Platform
    from ms.tools.http import HttpClient

__all__ = ["MavenTool"]


class MavenTool(Tool):
    """Apache Maven - uses Maven Central XML API.

    Maven is special because:
    - Uses Maven Central metadata XML (not GitHub releases)
    - Platform-independent (same archive for all OS)
    - Binary is bin/mvn (or bin/mvn.cmd on Windows)
    - Archives have a root directory (apache-maven-{version}/) to strip
    """

    spec = ToolSpec(
        id="maven",
        name="Apache Maven",
        required_for=frozenset({Mode.ENDUSER, Mode.DEV}),
    )

    # Major version prefix for version filtering
    major_prefix: str = "3.9"

    def latest_version(self, http: HttpClient) -> Result[str, HttpError]:
        """Fetch latest Maven version from Maven Central metadata."""
        return maven_latest_version(http, self.major_prefix)

    def download_url(self, version: str, platform: Platform, arch: Arch) -> str:
        """Get download URL for Maven.

        Maven is platform-independent, so same URL for all platforms.
        """
        # Use archive.apache.org for reproducibility (dlcdn may not keep older versions).
        return f"https://archive.apache.org/dist/maven/maven-3/{version}/binaries/apache-maven-{version}-bin.tar.gz"

    def strip_components(self) -> int:
        """Maven archives have a root directory to strip."""
        return 1

    def bin_path(self, tools_dir: Path, platform: Platform) -> Path | None:
        """Maven binary is in bin/mvn (or mvn.cmd on Windows).

        Note: On Windows, both mvn and mvn.cmd exist; we use mvn.cmd.
        """
        if platform == platform.WINDOWS:
            return tools_dir / "maven" / "bin" / "mvn.cmd"
        return tools_dir / "maven" / "bin" / "mvn"

    def post_install(self, install_dir: Path, platform: Platform) -> None:
        """Make scripts executable on Unix."""
        if platform.is_unix:
            bin_dir = install_dir / "bin"
            if bin_dir.exists():
                for script in bin_dir.iterdir():
                    if script.is_file() and script.suffix != ".cmd":
                        script.chmod(0o755)

    def m2_home(self, tools_dir: Path) -> Path:
        """Get M2_HOME path for this Maven installation.

        This is used by shell activation scripts to set M2_HOME.
        """
        return tools_dir / "maven"
