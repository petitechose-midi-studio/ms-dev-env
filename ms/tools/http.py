"""HTTP client abstraction for tools downloads.

This module provides:
- HttpClient: Protocol for HTTP operations (injectable for tests)
- RealHttpClient: Real implementation using urllib
- MockHttpClient: Mock implementation for testing
"""

from __future__ import annotations

import json
import ssl
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol, cast, runtime_checkable

from ms.core.result import Err, Ok, Result
from ms.core.structured import as_str_dict

if TYPE_CHECKING:
    from collections.abc import Callable

__all__ = [
    "HttpClient",
    "RealHttpClient",
    "MockHttpClient",
    "HttpError",
]


@dataclass(frozen=True, slots=True)
class HttpError:
    """HTTP error details.

    Attributes:
        url: The URL that failed
        status: HTTP status code (0 for network errors)
        message: Human-readable error message
    """

    url: str
    status: int
    message: str

    def __str__(self) -> str:
        if self.status:
            return f"HTTP {self.status}: {self.message} ({self.url})"
        return f"{self.message} ({self.url})"


@runtime_checkable
class HttpClient(Protocol):
    """Protocol for HTTP operations.

    This abstraction allows injecting mock clients for testing,
    avoiding real network calls in unit tests.
    """

    def get_json(self, url: str) -> Result[dict[str, Any], HttpError]:
        """Fetch URL and parse as JSON.

        Args:
            url: URL to fetch

        Returns:
            Ok with parsed JSON dict, or Err with HttpError
        """
        ...

    def get_text(self, url: str) -> Result[str, HttpError]:
        """Fetch URL and return as text.

        Args:
            url: URL to fetch

        Returns:
            Ok with response text, or Err with HttpError
        """
        ...

    def download(
        self,
        url: str,
        dest: Path,
        progress: Callable[[int, int], None] | None = None,
    ) -> Result[Path, HttpError]:
        """Download URL to file.

        Args:
            url: URL to download
            dest: Destination path
            progress: Optional callback(downloaded, total) for progress

        Returns:
            Ok with dest path, or Err with HttpError
        """
        ...


class RealHttpClient:
    """Real HTTP client using urllib.

    Handles:
    - HTTPS with system certificates
    - JSON parsing
    - Download with progress callback
    - Timeout handling
    """

    def __init__(self, timeout: float = 30.0, user_agent: str = "ms-cli/0.2.0") -> None:
        """Initialize HTTP client.

        Args:
            timeout: Request timeout in seconds
            user_agent: User-Agent header value
        """
        self.timeout = timeout
        self.user_agent = user_agent
        # Use system certificates
        self._ssl_context = ssl.create_default_context()

    def _request(self, url: str) -> Result[bytes, HttpError]:
        """Make HTTP GET request.

        Args:
            url: URL to fetch

        Returns:
            Ok with response bytes, or Err with HttpError
        """
        try:
            req = urllib.request.Request(
                url,
                headers={"User-Agent": self.user_agent},
            )
            with urllib.request.urlopen(
                req,
                timeout=self.timeout,
                context=self._ssl_context,
            ) as response:
                return Ok(response.read())
        except urllib.error.HTTPError as e:
            return Err(HttpError(url=url, status=e.code, message=e.reason))
        except urllib.error.URLError as e:
            return Err(HttpError(url=url, status=0, message=str(e.reason)))
        except TimeoutError:
            return Err(HttpError(url=url, status=0, message="Request timed out"))
        except ValueError as e:
            return Err(HttpError(url=url, status=0, message=str(e)))
        except OSError as e:
            return Err(HttpError(url=url, status=0, message=str(e)))

    def get_json(self, url: str) -> Result[dict[str, Any], HttpError]:
        """Fetch URL and parse as JSON."""
        result = self._request(url)
        if isinstance(result, Err):
            return result

        try:
            data_obj: object = json.loads(result.value.decode("utf-8"))
            data = as_str_dict(data_obj)
            if data is None:
                return Err(HttpError(url=url, status=0, message="Expected JSON object"))
            # Values are dynamic; preserve as Any for callers.
            return Ok(cast(dict[str, Any], data))
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            return Err(HttpError(url=url, status=0, message=f"JSON parse error: {e}"))

    def get_text(self, url: str) -> Result[str, HttpError]:
        """Fetch URL and return as text."""
        result = self._request(url)
        if isinstance(result, Err):
            return result

        try:
            return Ok(result.value.decode("utf-8"))
        except UnicodeDecodeError as e:
            return Err(HttpError(url=url, status=0, message=f"Decode error: {e}"))

    def download(
        self,
        url: str,
        dest: Path,
        progress: Callable[[int, int], None] | None = None,
    ) -> Result[Path, HttpError]:
        """Download URL to file with optional progress callback."""
        try:
            req = urllib.request.Request(
                url,
                headers={"User-Agent": self.user_agent},
            )
            with urllib.request.urlopen(
                req,
                timeout=self.timeout,
                context=self._ssl_context,
            ) as response:
                total = int(response.headers.get("Content-Length", 0))
                downloaded = 0
                chunk_size = 8192

                # Ensure parent directory exists
                dest.parent.mkdir(parents=True, exist_ok=True)

                with open(dest, "wb") as f:
                    while True:
                        chunk = response.read(chunk_size)
                        if not chunk:
                            break
                        f.write(chunk)
                        downloaded += len(chunk)
                        if progress:
                            progress(downloaded, total)

                return Ok(dest)

        except urllib.error.HTTPError as e:
            return Err(HttpError(url=url, status=e.code, message=e.reason))
        except urllib.error.URLError as e:
            return Err(HttpError(url=url, status=0, message=str(e.reason)))
        except TimeoutError:
            return Err(HttpError(url=url, status=0, message="Download timed out"))
        except ValueError as e:
            return Err(HttpError(url=url, status=0, message=str(e)))
        except OSError as e:
            return Err(HttpError(url=url, status=0, message=str(e)))


class MockHttpClient:
    """Mock HTTP client for testing.

    Allows setting predefined responses for specific URLs.

    Usage:
        client = MockHttpClient()
        client.set_json("https://api.example.com/data", {"key": "value"})
        result = client.get_json("https://api.example.com/data")
        assert result == Ok({"key": "value"})
    """

    def __init__(self) -> None:
        self._json_responses: dict[str, dict[str, Any] | HttpError] = {}
        self._text_responses: dict[str, str | HttpError] = {}
        self._download_responses: dict[str, bytes | HttpError] = {}
        self.calls: list[tuple[str, str]] = []

    def set_json(self, url: str, response: dict[str, Any] | HttpError) -> None:
        """Set JSON response for URL."""
        self._json_responses[url] = response

    def set_text(self, url: str, response: str | HttpError) -> None:
        """Set text response for URL."""
        self._text_responses[url] = response

    def set_download(self, url: str, response: bytes | HttpError) -> None:
        """Set download content for URL."""
        self._download_responses[url] = response

    def get_json(self, url: str) -> Result[dict[str, Any], HttpError]:
        """Get mocked JSON response."""
        self.calls.append(("get_json", url))

        if url not in self._json_responses:
            return Err(HttpError(url=url, status=404, message="Not found (mock)"))

        response = self._json_responses[url]
        if isinstance(response, HttpError):
            return Err(response)
        return Ok(response)

    def get_text(self, url: str) -> Result[str, HttpError]:
        """Get mocked text response."""
        self.calls.append(("get_text", url))

        if url not in self._text_responses:
            return Err(HttpError(url=url, status=404, message="Not found (mock)"))

        response = self._text_responses[url]
        if isinstance(response, HttpError):
            return Err(response)
        return Ok(response)

    def download(
        self,
        url: str,
        dest: Path,
        progress: Callable[[int, int], None] | None = None,
    ) -> Result[Path, HttpError]:
        """Mock download - writes predefined content to dest."""
        self.calls.append(("download", url))

        if url not in self._download_responses:
            return Err(HttpError(url=url, status=404, message="Not found (mock)"))

        response = self._download_responses[url]
        if isinstance(response, HttpError):
            return Err(response)

        # Write content to dest
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(response)

        # Call progress if provided
        if progress:
            progress(len(response), len(response))

        return Ok(dest)
