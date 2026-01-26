"""Tests for tools/download.py - Downloader with cache."""

from pathlib import Path

import pytest

from ms.core.result import Err, Ok
from ms.tools.download import DownloadResult, Downloader
from ms.tools.http import HttpError, MockHttpClient


class TestDownloadResult:
    """Tests for DownloadResult dataclass."""

    def test_create(self) -> None:
        """Create DownloadResult."""
        result = DownloadResult(
            path=Path("/cache/file.zip"),
            from_cache=True,
            size=1024,
        )
        assert result.path == Path("/cache/file.zip")
        assert result.from_cache is True
        assert result.size == 1024

    def test_is_frozen(self) -> None:
        """DownloadResult is immutable."""
        result = DownloadResult(path=Path("/cache/file.zip"), from_cache=True, size=1024)
        with pytest.raises(AttributeError):
            result.size = 2048  # type: ignore[misc]


class TestDownloaderCacheKey:
    """Tests for cache key generation."""

    def testcache_key_includes_filename(self, tmp_path: Path) -> None:
        """Cache key includes original filename."""
        downloader = Downloader(MockHttpClient(), tmp_path)

        key = downloader.cache_key("https://example.com/path/to/ninja-linux.zip")

        assert "ninja-linux.zip" in key

    def testcache_key_unique_per_url(self, tmp_path: Path) -> None:
        """Different URLs get different cache keys."""
        downloader = Downloader(MockHttpClient(), tmp_path)

        key1 = downloader.cache_key("https://example.com/v1/file.zip")
        key2 = downloader.cache_key("https://example.com/v2/file.zip")

        assert key1 != key2

    def testcache_key_same_for_same_url(self, tmp_path: Path) -> None:
        """Same URL always gets same cache key."""
        downloader = Downloader(MockHttpClient(), tmp_path)

        key1 = downloader.cache_key("https://example.com/file.zip")
        key2 = downloader.cache_key("https://example.com/file.zip")

        assert key1 == key2


class TestDownloaderDownload:
    """Tests for Downloader.download()."""

    def test_download_success(self, tmp_path: Path) -> None:
        """Download file successfully."""
        client = MockHttpClient()
        content = b"binary content here"
        client.set_download("https://example.com/file.zip", content)

        downloader = Downloader(client, tmp_path / "cache")
        result = downloader.download("https://example.com/file.zip")

        assert isinstance(result, Ok)
        assert result.value.from_cache is False
        assert result.value.size == len(content)
        assert result.value.path.exists()
        assert result.value.path.read_bytes() == content

    def test_download_from_cache(self, tmp_path: Path) -> None:
        """Return cached file on second download."""
        client = MockHttpClient()
        content = b"binary content"
        client.set_download("https://example.com/file.zip", content)

        downloader = Downloader(client, tmp_path / "cache")

        # First download
        result1 = downloader.download("https://example.com/file.zip")
        assert isinstance(result1, Ok)
        assert result1.value.from_cache is False

        # Second download should be from cache
        result2 = downloader.download("https://example.com/file.zip")
        assert isinstance(result2, Ok)
        assert result2.value.from_cache is True
        assert result2.value.path == result1.value.path

    def test_download_force_redownload(self, tmp_path: Path) -> None:
        """Force re-download even if cached."""
        client = MockHttpClient()
        content = b"original content"
        client.set_download("https://example.com/file.zip", content)

        downloader = Downloader(client, tmp_path / "cache")

        # First download
        result1 = downloader.download("https://example.com/file.zip")
        assert isinstance(result1, Ok)

        # Update mock content
        new_content = b"updated content"
        client.set_download("https://example.com/file.zip", new_content)

        # Force re-download
        result2 = downloader.download("https://example.com/file.zip", force=True)
        assert isinstance(result2, Ok)
        assert result2.value.from_cache is False
        assert result2.value.path.read_bytes() == new_content

    def test_download_network_error(self, tmp_path: Path) -> None:
        """Handle network error."""
        client = MockHttpClient()
        client.set_download(
            "https://example.com/error.zip",
            HttpError(url="https://example.com/error.zip", status=500, message="Server Error"),
        )

        downloader = Downloader(client, tmp_path / "cache")
        result = downloader.download("https://example.com/error.zip")

        assert isinstance(result, Err)
        assert result.error.status == 500

    def test_download_not_found(self, tmp_path: Path) -> None:
        """Handle 404 error."""
        client = MockHttpClient()
        # No mock set = 404

        downloader = Downloader(client, tmp_path / "cache")
        result = downloader.download("https://example.com/missing.zip")

        assert isinstance(result, Err)
        assert result.error.status == 404

    def test_download_creates_cache_dir(self, tmp_path: Path) -> None:
        """Cache directory is created if it doesn't exist."""
        client = MockHttpClient()
        client.set_download("https://example.com/file.zip", b"content")

        cache_dir = tmp_path / "deep" / "nested" / "cache"
        assert not cache_dir.exists()

        downloader = Downloader(client, cache_dir)
        result = downloader.download("https://example.com/file.zip")

        assert isinstance(result, Ok)
        assert cache_dir.exists()

    def test_download_with_progress(self, tmp_path: Path) -> None:
        """Progress callback is called."""
        client = MockHttpClient()
        content = b"x" * 1000
        client.set_download("https://example.com/file.zip", content)

        progress_calls: list[tuple[int, int]] = []

        def on_progress(downloaded: int, total: int) -> None:
            progress_calls.append((downloaded, total))

        downloader = Downloader(client, tmp_path / "cache")
        downloader.download("https://example.com/file.zip", progress=on_progress)

        assert len(progress_calls) > 0


class TestDownloaderCache:
    """Tests for cache management."""

    def test_is_cached_true(self, tmp_path: Path) -> None:
        """is_cached returns True for cached URLs."""
        client = MockHttpClient()
        client.set_download("https://example.com/file.zip", b"content")

        downloader = Downloader(client, tmp_path / "cache")
        downloader.download("https://example.com/file.zip")

        assert downloader.is_cached("https://example.com/file.zip") is True

    def test_is_cached_false(self, tmp_path: Path) -> None:
        """is_cached returns False for uncached URLs."""
        downloader = Downloader(MockHttpClient(), tmp_path / "cache")

        assert downloader.is_cached("https://example.com/file.zip") is False

    def test_get_cached_exists(self, tmp_path: Path) -> None:
        """get_cached returns path for cached URLs."""
        client = MockHttpClient()
        client.set_download("https://example.com/file.zip", b"content")

        downloader = Downloader(client, tmp_path / "cache")
        result = downloader.download("https://example.com/file.zip")
        assert isinstance(result, Ok)

        cached = downloader.get_cached("https://example.com/file.zip")
        assert cached is not None
        assert cached == result.value.path

    def test_get_cached_not_exists(self, tmp_path: Path) -> None:
        """get_cached returns None for uncached URLs."""
        downloader = Downloader(MockHttpClient(), tmp_path / "cache")

        cached = downloader.get_cached("https://example.com/file.zip")
        assert cached is None

    def test_clear_cache_specific_url(self, tmp_path: Path) -> None:
        """Clear cache for specific URL."""
        client = MockHttpClient()
        client.set_download("https://example.com/file1.zip", b"content1")
        client.set_download("https://example.com/file2.zip", b"content2")

        downloader = Downloader(client, tmp_path / "cache")
        downloader.download("https://example.com/file1.zip")
        downloader.download("https://example.com/file2.zip")

        # Clear only file1
        count = downloader.clear_cache("https://example.com/file1.zip")
        assert count == 1
        assert downloader.is_cached("https://example.com/file1.zip") is False
        assert downloader.is_cached("https://example.com/file2.zip") is True

    def test_clear_cache_all(self, tmp_path: Path) -> None:
        """Clear all cached files."""
        client = MockHttpClient()
        client.set_download("https://example.com/file1.zip", b"content1")
        client.set_download("https://example.com/file2.zip", b"content2")

        downloader = Downloader(client, tmp_path / "cache")
        downloader.download("https://example.com/file1.zip")
        downloader.download("https://example.com/file2.zip")

        count = downloader.clear_cache()
        assert count == 2
        assert downloader.is_cached("https://example.com/file1.zip") is False
        assert downloader.is_cached("https://example.com/file2.zip") is False
