from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Protocol, runtime_checkable

from ms.core.config import Config
from ms.core.workspace import Workspace


@dataclass(frozen=True, slots=True)
class ToolchainError:
    """Error from toolchain sync operations."""

    kind: Literal["sync_failed"]
    message: str
    hint: str | None = None


@runtime_checkable
class SystemToolProtocol(Protocol):
    def is_system_tool(self) -> bool: ...


@runtime_checkable
class GitInstallToolProtocol(Protocol):
    def uses_git_install(self) -> bool: ...

    def get_install_commands(self, tools_dir: Path, platform: object) -> list[list[str]]: ...


def is_system_tool(tool: object) -> bool:
    return isinstance(tool, SystemToolProtocol) and tool.is_system_tool()


def uses_git_install(tool: object) -> bool:
    return isinstance(tool, GitInstallToolProtocol) and tool.uses_git_install()


def git_install_commands(
    tool: object,
    *,
    tools_dir: Path,
    platform: object,
) -> list[list[str]]:
    if not isinstance(tool, GitInstallToolProtocol):
        return []
    return tool.get_install_commands(tools_dir, platform)


@dataclass(frozen=True, slots=True)
class ToolchainPaths:
    tools_dir: Path
    bin_dir: Path
    cache_downloads: Path

    @classmethod
    def from_workspace(cls, workspace: Workspace, config: Config | None) -> ToolchainPaths:
        tools_dir = workspace.root / (config.paths.tools if config else "tools")
        return cls(
            tools_dir=tools_dir,
            bin_dir=tools_dir / "bin",
            cache_downloads=workspace.download_cache_dir,
        )
