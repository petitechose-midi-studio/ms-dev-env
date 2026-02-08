"""Tools infrastructure for MIDI Studio CLI.

This package provides the tool management system including:
- Tool specifications and base class (base.py)
- HTTP client for downloads (http.py)
- Tool resolution (resolver.py)
- Download and installation (download.py, installer.py)
- Tool definitions (definitions/)
"""

from ms.tools.base import (
    Mode,
    Tool,
    ToolSpec,
)
from ms.tools.download import Downloader, DownloadResult
from ms.tools.github import GitHubTool
from ms.tools.http import (
    HttpClient,
    HttpError,
    MockHttpClient,
    RealHttpClient,
)
from ms.tools.installer import Installer, InstallError, InstallResult
from ms.tools.resolver import ResolvedTool, ToolNotFoundError, ToolResolver
from ms.tools.state import ToolState, get_installed_version, load_state, save_state

__all__ = [
    # Base types
    "Mode",
    "Tool",
    "ToolSpec",
    # Tool base classes
    "GitHubTool",
    # HTTP
    "HttpClient",
    "HttpError",
    "MockHttpClient",
    "RealHttpClient",
    # Download
    "Downloader",
    "DownloadResult",
    # Install
    "Installer",
    "InstallError",
    "InstallResult",
    # Resolve
    "ToolResolver",
    "ResolvedTool",
    "ToolNotFoundError",
    # State
    "ToolState",
    "load_state",
    "save_state",
    "get_installed_version",
]
