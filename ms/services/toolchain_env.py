"""Shared toolchain environment for build and test services."""

from __future__ import annotations

import os

from ms.core.workspace import Workspace
from ms.tools.registry import ToolRegistry


def base_env(*, registry: ToolRegistry, workspace: Workspace) -> dict[str, str]:
    """Base environment for toolchain commands (OS env + tool registry + PlatformIO)."""
    env = os.environ.copy()
    env.update(registry.get_env_vars())
    env.update(workspace.platformio_env_vars())
    return env
