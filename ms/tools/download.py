"""File downloader with caching support.

This module provides a Downloader class that:
- Downloads files from URLs
- Caches downloads in workspace/.ms/cache/downloads/
- Supports progress callbacks
- Returns Result for error handling
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING
from urllib.parse import urlparse

from ms.core.result import Err, Ok, Result
from ms.tools.http import HttpError

if TYPE_CHECKING:
    from collections.abc import Callable

    from ms.tools.http import HttpClient

__all__ = ["Downloader", "DownloadResult"]


@dataclass(frozen=True, slots=True)
class DownloadResult:
    """Result of a download operation.

    Attributes:
        path: Path to the downloaded file
        from_cache: True if file was served from cache
        size: File size in bytes
    """

    path: Path
    from_cache: bool
    size: int


class Downloader:
    """File downloader with caching.

    Downloads are cached in the workspace cache directory to avoid
    re-downloading the same files. Cache key is based on URL.

    Usage:
        downloader = Downloader(http_client, cache_dir)
        result = downloader.download(url)
        if is_ok(result):
            print(f"Downloaded to: {result.value.path}")
    """

    def __init__(self, http: HttpClient, cache_dir: Path) -> None:
        """Initialize downloader.

        Args:
            http: HTTP client for downloads
            cache_dir: Directory for cached downloads
        """
        self._http = http
        self._cache_dir = cache_dir

    @property
    def cache_dir(self) -> Path:
        """Get cache directory path."""
        return self._cache_dir

    def _cache_key(self, url: str) -> str:
        """Generate cache key for URL.

        Uses URL hash + filename to create unique but recognizable names.
        Example: "ninja-linux.zip" -> "a1b2c3d4_ninja-linux.zip"
        """
        # Get filename from URL
        parsed = urlparse(url)
        filename = Path(parsed.path).name or "download"

        # Create hash of full URL for uniqueness
        url_hash = hashlib.sha256(url.encode()).hexdigest()[:8]

        return f"{url_hash}_{filename}"

    def _cache_path(self, url: str) -> Path:
        """Get cache file path for URL."""
        return self._cache_dir / self._cache_key(url)

    def is_cached(self, url: str) -> bool:
        """Check if URL is already cached.

        Args:
            url: URL to check

        Returns:
            True if file exists in cache
        """
        return self._cache_path(url).exists()

    def get_cached(self, url: str) -> Path | None:
        """Get cached file path if exists.

        Args:
            url: URL to look up

        Returns:
            Path to cached file, or None if not cached
        """
        path = self._cache_path(url)
        return path if path.exists() else None

    def clear_cache(self, url: str | None = None) -> int:
        """Clear cached downloads.

        Args:
            url: Specific URL to clear, or None for all

        Returns:
            Number of files removed
        """
        if url is not None:
            path = self._cache_path(url)
            if path.exists():
                path.unlink()
                return 1
            return 0

        # Clear all cached files
        count = 0
        if self._cache_dir.exists():
            for file in self._cache_dir.iterdir():
                if file.is_file():
                    file.unlink()
                    count += 1
        return count

    def download(
        self,
        url: str,
        *,
        force: bool = False,
        progress: Callable[[int, int], None] | None = None,
    ) -> Result[DownloadResult, HttpError]:
        """Download file from URL.

        Args:
            url: URL to download
            force: If True, re-download even if cached
            progress: Optional callback(downloaded_bytes, total_bytes)

        Returns:
            Ok with DownloadResult, or Err with HttpError
        """
        cache_path = self._cache_path(url)

        # Check cache first
        if not force and cache_path.exists():
            size = cache_path.stat().st_size
            return Ok(DownloadResult(path=cache_path, from_cache=True, size=size))

        # Ensure cache directory exists
        self._cache_dir.mkdir(parents=True, exist_ok=True)

        # Download to cache
        result = self._http.download(url, cache_path, progress=progress)

        if isinstance(result, Err):
            # Clean up partial download
            if cache_path.exists():
                cache_path.unlink()
            return result

        size = cache_path.stat().st_size
        return Ok(DownloadResult(path=cache_path, from_cache=False, size=size))
