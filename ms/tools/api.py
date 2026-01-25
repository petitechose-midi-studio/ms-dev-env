"""External API functions for tool version resolution.

This module provides pure functions for querying external APIs:
- GitHub Releases API
- Adoptium JDK API
- Zig download index
- Maven Central metadata

All functions take an HttpClient parameter for testability.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any, cast

from ms.core.result import Err, Ok, Result
from ms.tools.http import HttpError

if TYPE_CHECKING:
    from ms.tools.http import HttpClient

__all__ = [
    "github_latest_release",
    "adoptium_jdk_url",
    "zig_latest_stable",
    "maven_latest_version",
]


def github_latest_release(http: HttpClient, repo: str) -> Result[str, HttpError]:
    """Fetch latest release version from GitHub.

    Args:
        http: HTTP client to use
        repo: Repository in "owner/repo" format (e.g., "ninja-build/ninja")

    Returns:
        Ok with version string (without 'v' prefix), or Err with HttpError

    Example:
        >>> client = RealHttpClient()
        >>> result = github_latest_release(client, "ninja-build/ninja")
        >>> if is_ok(result):
        ...     print(f"Latest version: {result.value}")  # e.g., "1.12.1"
    """
    url = f"https://api.github.com/repos/{repo}/releases/latest"
    result = http.get_json(url)

    if isinstance(result, Err):
        return result

    data = result.value
    tag_name = data.get("tag_name")
    if not isinstance(tag_name, str):
        return Err(HttpError(url=url, status=0, message="Missing tag_name in response"))

    # Strip 'v' prefix if present
    version = tag_name.lstrip("v")
    return Ok(version)


def adoptium_jdk_url(
    http: HttpClient,
    major: int,
    os: str,
    arch: str,
) -> Result[tuple[str, str], HttpError]:
    """Fetch JDK download URL from Adoptium API.

    Args:
        http: HTTP client to use
        major: JDK major version (e.g., 21, 25)
        os: Operating system ("linux", "mac", "windows")
        arch: Architecture ("x64", "aarch64")

    Returns:
        Ok with (download_url, version_string), or Err with HttpError

    Example:
        >>> client = RealHttpClient()
        >>> result = adoptium_jdk_url(client, 21, "linux", "x64")
        >>> if is_ok(result):
        ...     url, version = result.value
        ...     print(f"JDK {version}: {url}")
    """
    import json

    url = (
        f"https://api.adoptium.net/v3/assets/latest/{major}/hotspot"
        f"?architecture={arch}&image_type=jdk&os={os}&vendor=eclipse"
    )

    # Adoptium API returns an array, so we use get_text and parse manually
    text_result = http.get_text(url)
    if isinstance(text_result, Err):
        return text_result

    try:
        raw_data = json.loads(text_result.value)
    except json.JSONDecodeError as e:
        return Err(HttpError(url=url, status=0, message=f"JSON parse error: {e}"))

    # Validate response is a non-empty list
    if not isinstance(raw_data, list):
        return Err(HttpError(url=url, status=0, message="Expected JSON array"))
    data = cast(list[dict[str, Any]], raw_data)
    if len(data) == 0:
        return Err(HttpError(url=url, status=0, message="No JDK releases found"))

    # Get first (latest) release
    release: dict[str, Any] = data[0]

    binary: dict[str, Any] | None = release.get("binary")
    if not isinstance(binary, dict):
        return Err(HttpError(url=url, status=0, message="Missing binary info"))

    package: dict[str, Any] | None = binary.get("package")
    if not isinstance(package, dict):
        return Err(HttpError(url=url, status=0, message="Missing package info"))

    download_link: str | None = package.get("link")
    if not isinstance(download_link, str):
        return Err(HttpError(url=url, status=0, message="Missing download link"))

    # Get version info
    version_data: dict[str, Any] | None = release.get("version")
    if isinstance(version_data, dict):
        semver: str = version_data.get("semver", "")
        if semver:
            return Ok((download_link, semver))

    # Fallback: extract version from release name
    release_name: str = release.get("release_name", f"jdk-{major}")
    return Ok((download_link, release_name))


def zig_latest_stable(http: HttpClient) -> Result[tuple[str, dict[str, Any]], HttpError]:
    """Fetch latest stable Zig version and download URLs.

    Args:
        http: HTTP client to use

    Returns:
        Ok with (version, platform_urls), or Err with HttpError
        platform_urls is a dict mapping platform keys to URL info

    Example:
        >>> client = RealHttpClient()
        >>> result = zig_latest_stable(client)
        >>> if is_ok(result):
        ...     version, urls = result.value
        ...     print(f"Zig {version}")
        ...     linux_url = urls.get("x86_64-linux", {}).get("tarball")
    """
    url = "https://ziglang.org/download/index.json"
    result = http.get_json(url)

    if isinstance(result, Err):
        return result

    data: dict[str, Any] = result.value

    # Find latest stable version (not "master")
    # The JSON has version keys like "0.13.0", "0.12.0", "master"
    stable_versions: list[tuple[str, dict[str, Any]]] = [
        (k, v) for k, v in data.items() if k != "master" and isinstance(v, dict)
    ]

    if not stable_versions:
        return Err(HttpError(url=url, status=0, message="No stable versions found"))

    # Sort by version (semantic versioning)
    def version_key(item: tuple[str, dict[str, Any]]) -> tuple[int, ...]:
        try:
            parts = item[0].split(".")
            return tuple(int(p) for p in parts)
        except ValueError:
            return (0,)

    stable_versions.sort(key=version_key, reverse=True)
    latest_version: str
    platform_urls: dict[str, Any]
    latest_version, platform_urls = stable_versions[0]

    return Ok((latest_version, platform_urls))


def maven_latest_version(
    http: HttpClient,
    major_prefix: str = "3.9",
) -> Result[str, HttpError]:
    """Fetch latest Maven version from Maven Central.

    Args:
        http: HTTP client to use
        major_prefix: Version prefix to match (e.g., "3.9" for 3.9.x)

    Returns:
        Ok with version string (e.g., "3.9.6"), or Err with HttpError

    Example:
        >>> client = RealHttpClient()
        >>> result = maven_latest_version(client)
        >>> if is_ok(result):
        ...     print(f"Maven {result.value}")  # e.g., "3.9.6"
    """
    url = "https://repo1.maven.org/maven2/org/apache/maven/apache-maven/maven-metadata.xml"
    result = http.get_text(url)

    if isinstance(result, Err):
        return result

    xml_content = result.value

    # Parse versions from XML using regex (avoid xml.etree dependency)
    # Format: <version>3.9.6</version>
    version_pattern = re.compile(r"<version>([0-9.]+)</version>")
    versions = version_pattern.findall(xml_content)

    if not versions:
        return Err(HttpError(url=url, status=0, message="No versions found in metadata"))

    # Filter by major prefix and get latest
    matching = [v for v in versions if v.startswith(major_prefix)]
    if not matching:
        # Fallback: return latest overall version
        matching = versions

    # Sort by version
    def version_key(v: str) -> tuple[int, ...]:
        try:
            return tuple(int(p) for p in v.split("."))
        except ValueError:
            return (0,)

    matching.sort(key=version_key, reverse=True)
    return Ok(matching[0])
