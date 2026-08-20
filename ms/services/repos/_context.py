from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

    from ms.core.workspace import Workspace
    from ms.output.console import ConsoleProtocol
    from ms.platform.detection import Platform


class RepoContextBase:
    _workspace: Workspace
    _console: ConsoleProtocol
    _manifest_paths: tuple[Path, ...]
    _platform: Platform
