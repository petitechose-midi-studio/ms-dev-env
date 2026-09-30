from __future__ import annotations

from ms.core.config import Config
from ms.core.result import Result
from ms.core.workspace import Workspace
from ms.output.console import ConsoleProtocol
from ms.platform.detection import PlatformInfo
from ms.tools.registry import ToolRegistry

from .models import (
    ToolchainError,
    ToolchainPaths,
    git_install_commands,
    is_system_tool,
    uses_git_install,
)
from .sync import ToolchainSync


class ToolchainService:
    """Select tool sets and assemble their synchronization dependencies."""

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
        self._config: Config = config if config is not None else Config()
        self._console = console

        self._paths = ToolchainPaths.from_workspace(workspace, self._config)
        self._registry = ToolRegistry(
            tools_dir=self._paths.tools_dir,
            platform=platform.platform,
        )
        self._sync = ToolchainSync(
            workspace=workspace,
            platform=platform,
            paths=self._paths,
            registry=self._registry,
            console=console,
        )

    def sync_dev(
        self, *, dry_run: bool = False, force: bool = False
    ) -> Result[None, ToolchainError]:
        tool_ids = tuple(
            tool.spec.id for tool in self._registry.tools() if not is_system_tool(tool)
        )
        return self._sync.sync_tools(tool_ids=tool_ids, dry_run=dry_run, force=force)

    def sync_unit_tests(
        self, *, dry_run: bool = False, force: bool = False
    ) -> Result[None, ToolchainError]:
        tool_ids = ["cmake", "ninja"]
        if self._platform.platform.is_windows:
            tool_ids.append("zig")
        return self._sync.sync_tools(tool_ids=tuple(tool_ids), dry_run=dry_run, force=force)

    def needs_git_for_sync_dev(self) -> bool:
        for tool in self._registry.tools():
            if is_system_tool(tool):
                continue
            if uses_git_install(tool):
                cmds = git_install_commands(
                    tool, tools_dir=self._paths.tools_dir, platform=self._platform.platform,
                )
                if any(cmd and cmd[0] == "git" for cmd in cmds):
                    return True
        return False
