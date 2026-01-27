"""External API functions for tool version resolution.

This module provides pure functions for querying external APIs:
- GitHub Releases API
- Adoptium JDK API
- Maven Central metadata

All functions take an HttpClient parameter for testability.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from ms.core.result import Err, Ok, Result
from ms.core.structured import as_obj_list, as_str_dict, get_str, get_table
from ms.tools.http import HttpError

if TYPE_CHECKING:
    from ms.tools.http import HttpClient

__all__ = [
    "github_latest_release",
    "adoptium_jdk_url",
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
    releases = as_obj_list(raw_data)
    if releases is None:
        return Err(HttpError(url=url, status=0, message="Expected JSON array"))
    if len(releases) == 0:
        return Err(HttpError(url=url, status=0, message="No JDK releases found"))

    # Get first (latest) release
    release = as_str_dict(releases[0])
    if release is None:
        return Err(HttpError(url=url, status=0, message="Invalid release payload"))

    binary = get_table(release, "binary")
    if binary is None:
        return Err(HttpError(url=url, status=0, message="Missing binary info"))

    package = get_table(binary, "package")
    if package is None:
        return Err(HttpError(url=url, status=0, message="Missing package info"))

    download_link = get_str(package, "link")
    if not download_link:
        return Err(HttpError(url=url, status=0, message="Missing download link"))

    # Get version info
    version_table = get_table(release, "version")
    if version_table is not None:
        semver = get_str(version_table, "semver")
        if semver:
            return Ok((download_link, semver))

    # Fallback: extract version from release name
    release_name = get_str(release, "release_name") or f"jdk-{major}"
    return Ok((download_link, release_name))


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
