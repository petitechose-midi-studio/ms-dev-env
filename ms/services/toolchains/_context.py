from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ms.core.config import Config
    from ms.core.workspace import Workspace
    from ms.output.console import ConsoleProtocol
    from ms.platform.detection import PlatformInfo
    from ms.tools.registry import ToolRegistry

    from .models import ToolchainPaths


class ToolchainContextBase:
    _workspace: Workspace
    _platform: PlatformInfo
    _config: Config | None
    _console: ConsoleProtocol
    _registry: ToolRegistry
    _paths: ToolchainPaths
