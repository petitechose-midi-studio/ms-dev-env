from __future__ import annotations

from ms.core.config import Config
from ms.core.workspace import Workspace
from ms.output.console import ConsoleProtocol
from ms.platform.detection import PlatformInfo
from ms.tools.registry import ToolRegistry

from .models import ToolchainPaths
from .sync import ToolchainSyncMixin


class ToolchainService(ToolchainSyncMixin):
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

        self._paths = ToolchainPaths.from_workspace(workspace, config)
        self._registry = ToolRegistry(
            tools_dir=self._paths.tools_dir,
            platform=platform.platform,
            arch=platform.arch,
        )
