from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from ms.core.result import Err, Ok, Result
from ms.core.workspace import Workspace, find_workspace_upward

PlatformioRuntimeSource = Literal["workspace_venv", "current_python"]


@dataclass(frozen=True, slots=True)
class PlatformioRuntimeError:
    message: str
    hint: str | None = None


@dataclass(frozen=True, slots=True)
class PlatformioRuntime:
    python_executable: Path
    env: dict[str, str]
    source: PlatformioRuntimeSource
    workspace_root: Path | None

    def command(self, *args: str) -> list[str]:
        return [str(self.python_executable), "-m", "platformio", *args]


def resolve_platformio_runtime(
    start: Path,
    *,
    current_python: Path | None = None,
    tools_dir: Path | None = None,
) -> Result[PlatformioRuntime, PlatformioRuntimeError]:
    workspace_root = find_workspace_upward(start.resolve())
    env = dict(os.environ)

    if workspace_root is None:
        python = (current_python or Path(sys.executable)).resolve()
        return Ok(
            PlatformioRuntime(
                python_executable=python,
                env=env,
                source="current_python",
                workspace_root=None,
            )
        )

    workspace = Workspace(root=workspace_root)
    env.update(workspace.platformio_env_vars())

    effective_tools = tools_dir if tools_dir is not None else workspace_root / "tools"
    python = _workspace_platformio_python(effective_tools)
    if not python.exists():
        return Err(
            PlatformioRuntimeError(
                message=f"workspace PlatformIO runtime missing: {python}",
                hint="Run: uv run ms sync --tools",
            )
        )

    return Ok(
        PlatformioRuntime(
            python_executable=python,
            env=env,
            source="workspace_venv",
            workspace_root=workspace_root,
        )
    )


def _workspace_platformio_python(tools_dir: Path) -> Path:
    venv_dir = tools_dir / "platformio" / "venv"
    if os.name == "nt":
        return venv_dir / "Scripts" / "python.exe"
    return venv_dir / "bin" / "python"
