from __future__ import annotations

from pathlib import Path

from ms.core.config import CONTROLLER_CORE_NATIVE_PORT, Config
from ms.core.result import Result
from ms.core.workspace import Workspace
from ms.output.console import ConsoleProtocol
from ms.platform.detection import PlatformInfo
from ms.services.base import BaseService
from ms.services.build_errors import BuildError

from .runtime import BuildRuntime
from .targets import BuildTargets


class BuildService(BaseService):
    """Build service for native and WASM targets."""

    def __init__(
        self,
        *,
        workspace: Workspace,
        platform: PlatformInfo,
        config: Config | None,
        console: ConsoleProtocol,
    ) -> None:
        super().__init__(workspace=workspace, platform=platform, config=config, console=console)
        self._targets = BuildTargets(
            workspace=workspace,
            platform=platform,
            console=console,
            registry=self._registry,
        )
        self._runtime = BuildRuntime(
            targets=self._targets,
            workspace=workspace,
            platform=platform,
            config=self._config,
            console=console,
        )

    def build_core_file_tool(self, *, dry_run: bool = False) -> Result[Path, BuildError]:
        return self._targets.build_core_file_tool(dry_run=dry_run)

    def build_native(self, *, app_name: str, dry_run: bool = False) -> Result[Path, BuildError]:
        return self._targets.build_native(app_name=app_name, dry_run=dry_run)

    def build_wasm(self, *, app_name: str, dry_run: bool = False) -> Result[Path, BuildError]:
        return self._targets.build_wasm(app_name=app_name, dry_run=dry_run)

    def run_native(self, *, app_name: str) -> int:
        return self._runtime.run_native(app_name=app_name)

    def serve_wasm(self, *, app_name: str, port: int = CONTROLLER_CORE_NATIVE_PORT) -> int:
        return self._runtime.serve_wasm(app_name=app_name, port=port)
