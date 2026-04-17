from __future__ import annotations

import os
from pathlib import Path

from ms.core.platformio_runtime import (
    PlatformioRuntime,
    PlatformioRuntimeError,
    resolve_platformio_runtime,
)
from ms.core.result import Err, Result
from rich.console import Console

from .models import OCPlatform


def get_console() -> Console:
    return Console(highlight=False)


def find_project_root(start: Path | None = None) -> Path:
    base = (start or Path.cwd()).resolve()
    for parent in (base, *base.parents):
        if (parent / "platformio.ini").is_file():
            return parent
    raise FileNotFoundError("platformio.ini not found (run from project directory)")


def _find_workspace_root(start: Path) -> Path | None:
    base = start.resolve()
    for parent in (base, *base.parents):
        if (parent / ".ms-workspace").is_file():
            return parent
    return None


def build_pio_env(start: Path, platform: OCPlatform) -> dict[str, str]:
    del platform
    runtime = resolve_pio_runtime(start)
    if isinstance(runtime, Err):
        env = dict(os.environ)
        workspace = _find_workspace_root(start)
        if workspace is None:
            return env

        ms_state = workspace / ".ms"
        env.setdefault("PLATFORMIO_CORE_DIR", str(ms_state / "platformio"))
        env.setdefault("PLATFORMIO_CACHE_DIR", str(ms_state / "platformio-cache"))
        env.setdefault("PLATFORMIO_BUILD_CACHE_DIR", str(ms_state / "platformio-build-cache"))
        return env
    return runtime.value.env


def resolve_pio_runtime(start: Path) -> Result[PlatformioRuntime, PlatformioRuntimeError]:
    return resolve_platformio_runtime(start)


def detect_env(project_root: Path, explicit: str | None) -> str:
    if explicit:
        return explicit

    build_dir = project_root / ".pio" / "build"
    if build_dir.is_dir():
        dirs = [path for path in build_dir.iterdir() if path.is_dir() and path.name != "build"]
        if dirs:
            dirs.sort(key=lambda path: path.stat().st_mtime, reverse=True)
            return dirs[0].name

    ini = project_root / "platformio.ini"
    try:
        for line in ini.read_text(encoding="utf-8", errors="replace").splitlines():
            raw = line.strip()
            if not raw or raw.startswith(";") or raw.startswith("#"):
                continue
            if raw.startswith("default_envs"):
                _, _, rhs = raw.partition("=")
                candidates = [candidate.strip() for candidate in rhs.split(",")]
                for candidate in candidates:
                    if candidate:
                        return candidate.split()[0]
    except OSError:
        pass

    return "dev"
