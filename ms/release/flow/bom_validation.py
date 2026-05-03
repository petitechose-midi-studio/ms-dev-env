from __future__ import annotations

import sys
import time
from dataclasses import dataclass
from pathlib import Path

from ms.core.platformio_runtime import resolve_platformio_runtime
from ms.core.result import Err, Ok, Result
from ms.output.console import ConsoleProtocol, Style
from ms.platform.process import run as run_process
from ms.release.errors import ReleaseError

_PLATFORMIO_TIMEOUT_SECONDS = 30 * 60.0


@dataclass(frozen=True, slots=True)
class BomValidationTarget:
    key: str
    label: str
    cwd: Path
    command: tuple[str, ...]


def validate_workspace_bom_targets(
    *,
    workspace_root: Path,
    include_plugin_release: bool = True,
    console: ConsoleProtocol | None = None,
) -> Result[tuple[BomValidationTarget, ...], ReleaseError]:
    runtime = resolve_platformio_runtime(workspace_root)
    if isinstance(runtime, Err):
        return Err(
            ReleaseError(
                kind="invalid_input",
                message=runtime.error.message,
                hint=runtime.error.hint,
            )
        )

    runtime_command = tuple(runtime.value.command())
    ms_command = (sys.executable, "-c", "from ms.cli.app import main; main()")
    targets = list(
        _validation_targets(
            workspace_root=workspace_root,
            command=runtime_command,
            ms_command=ms_command,
        )
    )
    if not include_plugin_release:
        targets = [target for target in targets if not target.key.startswith("plugin-bitwig-")]

    return _run_validation_targets(targets=tuple(targets), env=runtime.value.env, console=console)


def validate_workspace_dev_targets(
    *, workspace_root: Path, console: ConsoleProtocol | None = None
) -> Result[tuple[BomValidationTarget, ...], ReleaseError]:
    runtime = resolve_platformio_runtime(workspace_root)
    if isinstance(runtime, Err):
        return Err(
            ReleaseError(
                kind="invalid_input",
                message=runtime.error.message,
                hint=runtime.error.hint,
            )
        )

    runtime_command = tuple(runtime.value.command())
    ms_command = (sys.executable, "-c", "from ms.cli.app import main; main()")
    core_root = workspace_root / "midi-studio" / "core"
    plugin_root = workspace_root / "midi-studio" / "plugin-bitwig"

    targets = (
        BomValidationTarget(
            key="core-dev",
            label="core dev",
            cwd=core_root,
            command=(*runtime_command, "run", "-e", "dev"),
        ),
        BomValidationTarget(
            key="plugin-bitwig-dev",
            label="plugin-bitwig dev",
            cwd=plugin_root,
            command=(*runtime_command, "run", "-e", "dev"),
        ),
        BomValidationTarget(
            key="workspace-unit-tests",
            label="workspace unit tests",
            cwd=workspace_root,
            command=(*ms_command, "test", "all"),
        ),
    )
    return _run_validation_targets(targets=targets, env=runtime.value.env, console=console)


def _run_validation_targets(
    *,
    targets: tuple[BomValidationTarget, ...],
    env: dict[str, str],
    console: ConsoleProtocol | None,
) -> Result[tuple[BomValidationTarget, ...], ReleaseError]:
    validated: list[BomValidationTarget] = []
    if console is not None:
        console.header("Validation")
    total = len(targets)
    for index, target in enumerate(targets, start=1):
        if console is not None:
            console.print(f"[{index}/{total}] running {target.label}", Style.INFO)
            console.print(f"cwd: {target.cwd}", Style.DIM)
            console.print(f"cmd: {_format_command(target.command)}", Style.DIM)
        started_at = time.perf_counter()
        result = run_process(
            list(target.command),
            cwd=target.cwd,
            env=env,
            timeout=_PLATFORMIO_TIMEOUT_SECONDS,
        )
        elapsed = time.perf_counter() - started_at
        if isinstance(result, Err):
            if console is not None:
                console.error(f"{target.label} failed after {elapsed:.1f}s")
            return Err(
                ReleaseError(
                    kind="repo_failed",
                    message=f"{target.label} failed",
                    hint=_process_hint(result.error.stdout, result.error.stderr),
                )
            )
        if console is not None:
            console.success(f"{target.label} ({elapsed:.1f}s)")
        validated.append(target)

    return Ok(tuple(validated))


def _validation_targets(
    *, workspace_root: Path, command: tuple[str, ...], ms_command: tuple[str, ...]
) -> tuple[BomValidationTarget, ...]:
    core_root = workspace_root / "midi-studio" / "core"
    plugin_root = workspace_root / "midi-studio" / "plugin-bitwig"

    return (
        BomValidationTarget(
            key="core-release",
            label="core release",
            cwd=core_root,
            command=(*command, "run", "-e", "release"),
        ),
        BomValidationTarget(
            key="core-unit-tests",
            label="core unit tests",
            cwd=workspace_root,
            command=(*ms_command, "test", "core"),
        ),
        BomValidationTarget(
            key="plugin-bitwig-release",
            label="plugin-bitwig release",
            cwd=plugin_root,
            command=(*command, "run", "-e", "release"),
        ),
        BomValidationTarget(
            key="plugin-bitwig-unit-tests",
            label="plugin-bitwig unit tests",
            cwd=workspace_root,
            command=(*ms_command, "test", "plugin-bitwig"),
        ),
    )


def _process_hint(stdout: str, stderr: str) -> str | None:
    text = (stderr or stdout).strip()
    if not text:
        return None
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        return None
    hint = lines[-1]
    if len(hint) > 300:
        return hint[:297] + "..."
    return hint


def _format_command(command: tuple[str, ...]) -> str:
    return " ".join(command)


__all__ = [
    "BomValidationTarget",
    "validate_workspace_bom_targets",
    "validate_workspace_dev_targets",
]
