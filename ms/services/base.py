"""Base service class with common initialization."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ms.tools.registry import ToolRegistry

if TYPE_CHECKING:
    from ms.core.config import Config
    from ms.core.workspace import Workspace
    from ms.output.console import ConsoleProtocol
    from ms.platform.detection import PlatformInfo


class BaseService:
    """Base class for services that need workspace, platform, config, and console.

    Provides:
    - Common constructor pattern
    - ToolRegistry initialization
    - Access to workspace, platform, config, console
    """

    def __init__(
        self,
        *,
        workspace: Workspace,
        platform: PlatformInfo,
        config: Config | None,
        console: ConsoleProtocol,
    ) -> None:
        self._workspace = workspace
        self._platform = platform
        self._config = config
        self._console = console

        tools_dir = workspace.root / (config.paths.tools if config else "tools")
        self._registry = ToolRegistry(
            tools_dir=tools_dir,
            platform=platform.platform,
        )
