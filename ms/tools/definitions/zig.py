"""Zig compiler tool definition.

Zig is a systems programming language and compiler. It's used as a
cross-compiler for native builds in this project (via zig cc).

Website: https://ziglang.org/
API: https://ziglang.org/download/index.json
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ms.core.result import Err, Ok, Result
from ms.tools.api import zig_latest_stable
from ms.tools.base import Mode, Tool, ToolSpec
from ms.tools.http import HttpError

if TYPE_CHECKING:
    from pathlib import Path

    from ms.platform.detection import Arch, Platform
    from ms.tools.http import HttpClient

__all__ = ["ZigTool"]


# Platform mapping: (Platform, Arch) -> Zig platform string
_ZIG_PLATFORMS: dict[tuple[str, str], str] = {
    ("linux", "x64"): "x86_64-linux",
    ("linux", "arm64"): "aarch64-linux",
    ("macos", "x64"): "x86_64-macos",
    ("macos", "arm64"): "aarch64-macos",
    ("windows", "x64"): "x86_64-windows",
    ("windows", "arm64"): "aarch64-windows",
}


class ZigTool(Tool):
    """Zig compiler - uses custom API (not GitHub).

    Zig releases are fetched from ziglang.org/download/index.json.
    Archives have a root directory (zig-{platform}-{version}/) to strip.

    Note: zig-cc and zig-cxx wrappers are created separately by WrapperGenerator.
    """

    spec = ToolSpec(
        id="zig",
        name="Zig",
        required_for=frozenset({Mode.DEV}),
    )

    # Cache for platform URLs (set by latest_version)
    _platform_urls: dict[str, dict[str, str]] | None = None
    _cached_version: str | None = None

    def _get_zig_platform(self, platform: Platform, arch: Arch) -> str | None:
        """Get Zig platform string for Platform/Arch combo."""
        key = (str(platform).lower(), str(arch).lower())
        return _ZIG_PLATFORMS.get(key)

    def latest_version(self, http: HttpClient) -> Result[str, HttpError]:
        """Fetch latest stable version from ziglang.org.

        This also caches the platform URLs for use by download_url().
        """
        result = zig_latest_stable(http)

        if isinstance(result, Err):
            return result

        version, platform_urls = result.value
        self._cached_version = version
        self._platform_urls = platform_urls
        return Ok(version)

    def download_url(self, version: str, platform: Platform, arch: Arch) -> str:
        """Get download URL for specific version and platform.

        If latest_version() was called first, uses cached URLs.
        Otherwise, constructs URL from known pattern.
        """
        zig_platform = self._get_zig_platform(platform, arch)
        if zig_platform is None:
            # Fallback to Linux x64
            zig_platform = "x86_64-linux"

        # Try cached URLs first (from latest_version call)
        if (
            self._platform_urls is not None
            and self._cached_version == version
            and zig_platform in self._platform_urls
        ):
            url_info = self._platform_urls[zig_platform]
            if "tarball" in url_info:
                return str(url_info["tarball"])

        # Fallback: construct URL from pattern
        # Note: This may not always work as Zig URL patterns can change
        ext = "zip" if platform.name.lower() == "windows" else "tar.xz"
        return f"https://ziglang.org/download/{version}/zig-{zig_platform}-{version}.{ext}"

    def strip_components(self) -> int:
        """Zig archives have a root directory to strip."""
        return 1

    def bin_path(self, tools_dir: Path, platform: Platform) -> Path | None:
        """Zig binary is directly in the zig/ directory."""
        return tools_dir / "zig" / platform.exe_name("zig")

    def post_install(self, install_dir: Path, platform: Platform) -> None:
        """Make binary executable on Unix."""
        if platform.is_unix:
            bin_path = install_dir / platform.exe_name(self.spec.id)
            if bin_path.exists():
                bin_path.chmod(0o755)
