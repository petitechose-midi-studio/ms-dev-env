from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ms.core.config import Config
from ms.core.workspace import Workspace
from ms.platform.detection import PlatformInfo
from ms.services.checkers import (
    CheckResult,
    RuntimeChecker,
    SystemChecker,
    ToolsChecker,
    WorkspaceChecker,
    load_hints,
)


@dataclass(frozen=True, slots=True)
class CheckReport:
    workspace: list[CheckResult]
    tools: list[CheckResult]
    system: list[CheckResult]
    runtime: list[CheckResult]

    def all_results(self) -> list[CheckResult]:
        return [*self.workspace, *self.tools, *self.system, *self.runtime]

    def has_errors(self) -> bool:
        return any(r.is_error for r in self.all_results())


class CheckService:
    def __init__(
        self,
        *,
        workspace: Workspace,
        platform: PlatformInfo,
        config: Config | None,
    ) -> None:
        self._workspace = workspace
        self._platform = platform
        self._config: Config = config if config is not None else Config()

    def run(self) -> CheckReport:
        hints = load_hints()

        tools_dir = self._resolve_tools_dir()
        bitwig_paths = self.resolve_bitwig_paths()

        workspace_checker = WorkspaceChecker(
            workspace=self._workspace,
            platform=self._platform.platform,
            config=self._config,
            bitwig_paths=bitwig_paths,
        )

        tools_checker = ToolsChecker(
            platform=self._platform.platform,
            tools_dir=tools_dir,
            hints=hints,
            distro=self._platform.distro,
        )

        system_checker = SystemChecker(
            platform=self._platform.platform,
            distro=self._platform.distro,
            tools_dir=tools_dir,
            hints=hints,
        )

        runtime_checker = RuntimeChecker(
            platform=self._platform.platform,
            distro=self._platform.distro,
            hints=hints,
        )

        return CheckReport(
            workspace=workspace_checker.check_all(),
            tools=tools_checker.check_all(),
            system=system_checker.check_all(),
            runtime=runtime_checker.check_all(),
        )

    def _resolve_tools_dir(self) -> Path:
        return self._workspace.root / self._config.paths.tools

    def resolve_bitwig_paths(self) -> dict[str, str]:
        return self._config.bitwig.as_dict()
