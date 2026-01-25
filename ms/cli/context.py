from __future__ import annotations

from dataclasses import dataclass

import typer

from ms.core.config import Config, load_config
from ms.core.errors import ErrorCode
from ms.core.result import Err
from ms.core.workspace import Workspace, detect_workspace
from ms.output.console import ConsoleProtocol, RichConsole
from ms.platform.detection import PlatformInfo, detect


@dataclass(frozen=True, slots=True)
class CLIContext:
    workspace: Workspace
    platform: PlatformInfo
    config: Config | None
    console: ConsoleProtocol


def build_context() -> CLIContext:
    workspace_result = detect_workspace()
    if isinstance(workspace_result, Err):
        typer.echo(f"error: {workspace_result.error.message}", err=True)
        raise typer.Exit(code=int(ErrorCode.ENV_ERROR))

    workspace = workspace_result.value
    platform = detect()

    config: Config | None = None
    if workspace.config_path.exists():
        config_result = load_config(workspace.config_path)
        if not isinstance(config_result, Err):
            config = config_result.value

    return CLIContext(
        workspace=workspace,
        platform=platform,
        config=config,
        console=RichConsole(),
    )
