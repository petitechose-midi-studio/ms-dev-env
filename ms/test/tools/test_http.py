"""Tests for tools/http.py - HTTP client abstraction."""

from pathlib import Path

import pytest

from ms.core.result import Err, Ok
from ms.tools.http import (
    HttpClient,
    HttpError,
    MockHttpClient,
    RealHttpClient,
)


# =============================================================================
# HttpError tests
# =============================================================================


class TestHttpError:
    """Tests for HttpError dataclass."""

    def test_create_with_status(self) -> None:
        """Create error with HTTP status."""
        error = HttpError(url="https://example.com", status=404, message="Not Found")
        assert error.url == "https://example.com"
        assert error.status == 404
        assert error.message == "Not Found"

    def test_create_network_error(self) -> None:
        """Create error without HTTP status (network error)."""
        error = HttpError(url="https://example.com", status=0, message="Connection refused")
        assert error.status == 0
        assert error.message == "Connection refused"

    def test_str_with_status(self) -> None:
        """String representation includes status code."""
        error = HttpError(url="https://example.com/api", status=500, message="Internal Error")
        assert str(error) == "HTTP 500: Internal Error (https://example.com/api)"

    def test_str_without_status(self) -> None:
        """String representation without status code."""
        error = HttpError(url="https://example.com", status=0, message="Timeout")
        assert str(error) == "Timeout (https://example.com)"

    def test_is_frozen(self) -> None:
        """HttpError is immutable."""
        error = HttpError(url="https://example.com", status=404, message="Not Found")
        with pytest.raises(AttributeError):
            error.status = 500  # type: ignore[misc]


# =============================================================================
# MockHttpClient tests
# =============================================================================


class TestMockHttpClient:
    """Tests for MockHttpClient."""

    def test_isinstance_check(self) -> None:
        """MockHttpClient implements HttpClient protocol."""
        client = MockHttpClient()
        assert isinstance(client, HttpClient)

    def test_get_json_success(self) -> None:
        """get_json returns mocked JSON response."""
        client = MockHttpClient()
        client.set_json("https://api.example.com/data", {"key": "value", "count": 42})

        result = client.get_json("https://api.example.com/data")

        assert isinstance(result, Ok)
        assert result.value == {"key": "value", "count": 42}

    def test_get_json_not_found(self) -> None:
        """get_json returns error for unknown URL."""
        client = MockHttpClient()

        result = client.get_json("https://api.example.com/unknown")

        assert isinstance(result, Err)
        assert result.error.status == 404
        assert "Not found" in result.error.message

    def test_get_json_error_response(self) -> None:
        """get_json returns mocked error response."""
        client = MockHttpClient()
        client.set_json(
            "https://api.example.com/error",
            HttpError(url="https://api.example.com/error", status=500, message="Server Error"),
        )

        result = client.get_json("https://api.example.com/error")

        assert isinstance(result, Err)
        assert result.error.status == 500

    def test_get_text_success(self) -> None:
        """get_text returns mocked text response."""
        client = MockHttpClient()
        client.set_text("https://example.com/file.txt", "Hello, World!")

        result = client.get_text("https://example.com/file.txt")

        assert isinstance(result, Ok)
        assert result.value == "Hello, World!"

    def test_get_text_not_found(self) -> None:
        """get_text returns error for unknown URL."""
        client = MockHttpClient()

        result = client.get_text("https://example.com/unknown.txt")

        assert isinstance(result, Err)
        assert result.error.status == 404

    def test_get_text_error_response(self) -> None:
        """get_text returns mocked error response."""
        client = MockHttpClient()
        client.set_text(
            "https://example.com/error",
            HttpError(url="https://example.com/error", status=403, message="Forbidden"),
        )

        result = client.get_text("https://example.com/error")

        assert isinstance(result, Err)
        assert result.error.status == 403

    def test_download_success(self, tmp_path: Path) -> None:
        """download writes mocked content to file."""
        client = MockHttpClient()
        content = b"binary content here"
        client.set_download("https://example.com/file.zip", content)

        dest = tmp_path / "downloaded.zip"
        result = client.download("https://example.com/file.zip", dest)

        assert isinstance(result, Ok)
        assert result.value == dest
        assert dest.exists()
        assert dest.read_bytes() == content

    def test_download_creates_parent_dirs(self, tmp_path: Path) -> None:
        """download creates parent directories."""
        client = MockHttpClient()
        client.set_download("https://example.com/file.zip", b"content")

        dest = tmp_path / "nested" / "dir" / "file.zip"
        result = client.download("https://example.com/file.zip", dest)

        assert isinstance(result, Ok)
        assert dest.exists()

    def test_download_not_found(self, tmp_path: Path) -> None:
        """download returns error for unknown URL."""
        client = MockHttpClient()

        dest = tmp_path / "file.zip"
        result = client.download("https://example.com/unknown.zip", dest)

        assert isinstance(result, Err)
        assert result.error.status == 404
        assert not dest.exists()

    def test_download_error_response(self, tmp_path: Path) -> None:
        """download returns mocked error response."""
        client = MockHttpClient()
        client.set_download(
            "https://example.com/error.zip",
            HttpError(url="https://example.com/error.zip", status=503, message="Unavailable"),
        )

        dest = tmp_path / "file.zip"
        result = client.download("https://example.com/error.zip", dest)

        assert isinstance(result, Err)
        assert result.error.status == 503

    def test_download_with_progress(self, tmp_path: Path) -> None:
        """download calls progress callback."""
        client = MockHttpClient()
        content = b"x" * 1000
        client.set_download("https://example.com/file.zip", content)

        progress_calls: list[tuple[int, int]] = []

        def on_progress(downloaded: int, total: int) -> None:
            progress_calls.append((downloaded, total))

        dest = tmp_path / "file.zip"
        client.download("https://example.com/file.zip", dest, progress=on_progress)

        assert len(progress_calls) == 1
        assert progress_calls[0] == (1000, 1000)

    def test_tracks_calls(self) -> None:
        """MockHttpClient tracks all method calls."""
        client = MockHttpClient()
        client.set_json("https://api.example.com/1", {"a": 1})
        client.set_text("https://api.example.com/2", "text")

        client.get_json("https://api.example.com/1")
        client.get_text("https://api.example.com/2")
        client.get_json("https://api.example.com/unknown")

        assert client.calls == [
            ("get_json", "https://api.example.com/1"),
            ("get_text", "https://api.example.com/2"),
            ("get_json", "https://api.example.com/unknown"),
        ]


# =============================================================================
# RealHttpClient tests (unit tests only - no network)
# =============================================================================


class TestRealHttpClient:
    """Tests for RealHttpClient (no network calls)."""

    def test_isinstance_check(self) -> None:
        """RealHttpClient implements HttpClient protocol."""
        client = RealHttpClient()
        assert isinstance(client, HttpClient)

    def test_default_config(self) -> None:
        """RealHttpClient has sensible defaults."""
        client = RealHttpClient()
        assert client.timeout == 30.0
        assert "ms-cli" in client.user_agent

    def test_custom_config(self) -> None:
        """RealHttpClient accepts custom config."""
        client = RealHttpClient(timeout=60.0, user_agent="test-agent/1.0")
        assert client.timeout == 60.0
        assert client.user_agent == "test-agent/1.0"

    def test_get_json_invalid_url(self) -> None:
        """get_json handles invalid URL."""
        client = RealHttpClient(timeout=1.0)

        # Invalid URL format
        result = client.get_json("not-a-url")

        assert isinstance(result, Err)
        assert result.error.status == 0  # Network error, not HTTP error

    def test_get_text_invalid_url(self) -> None:
        """get_text handles invalid URL."""
        client = RealHttpClient(timeout=1.0)

        result = client.get_text("not-a-url")

        assert isinstance(result, Err)
        assert result.error.status == 0

    def test_download_invalid_url(self, tmp_path: Path) -> None:
        """download handles invalid URL."""
        client = RealHttpClient(timeout=1.0)

        dest = tmp_path / "file.zip"
        result = client.download("not-a-url", dest)

        assert isinstance(result, Err)
        assert result.error.status == 0
        assert not dest.exists()


# =============================================================================
# Integration tests (marked for optional execution)
# =============================================================================


@pytest.mark.network
class TestRealHttpClientIntegration:
    """Integration tests that make real network calls.

    Run with: pytest -m network
    Skip with: pytest -m "not network"
    """

    def test_get_json_real(self) -> None:
        """Real GET request for JSON."""
        client = RealHttpClient()

        # Use httpbin for testing
        result = client.get_json("https://httpbin.org/json")

        assert isinstance(result, Ok)
        assert "slideshow" in result.value

    def test_get_text_real(self) -> None:
        """Real GET request for text."""
        client = RealHttpClient()

        result = client.get_text("https://httpbin.org/robots.txt")

        assert isinstance(result, Ok)
        assert "User-agent" in result.value

    def test_download_real(self, tmp_path: Path) -> None:
        """Real file download."""
        client = RealHttpClient()

        dest = tmp_path / "robots.txt"
        result = client.download("https://httpbin.org/robots.txt", dest)

        assert isinstance(result, Ok)
        assert dest.exists()
        assert "User-agent" in dest.read_text()
