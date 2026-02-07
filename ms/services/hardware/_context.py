from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ms.core.workspace import Workspace
    from ms.output.console import ConsoleProtocol
    from ms.platform.detection import PlatformInfo


class HardwareContextBase:
    _workspace: Workspace
    _platform: PlatformInfo
    _console: ConsoleProtocol
