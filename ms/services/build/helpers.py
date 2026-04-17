from __future__ import annotations

import os
import shutil
from pathlib import Path

from ms.core.platformio_runtime import resolve_platformio_runtime
from ms.core.result import Err, Ok, Result
from ms.output.console import Style
from ms.output.errors import build_error_exit_code, print_build_error
from ms.platform.process import run_silent
from ms.services.build_errors import (
    AppConfigInvalid,
    BuildError,
    PrereqMissing,
    ToolMissing,
)
from ms.services.checkers.common import get_platform_key, load_hints

from ._context import BuildContextBase
from .models import AppConfig, extract_cmake_var

_PLATFORMIO_DEPS_TIMEOUT_SECONDS = 15 * 60.0


class BuildHelpersMixin(BuildContextBase):
    def _core_sdl_dir(self) -> Path:
        return self._workspace.midi_studio_dir / "core" / "sdl"

    def _base_env(self) -> dict[str, str]:
        env = os.environ.copy()
        env.update(self._registry.get_env_vars())
        env.update(self._workspace.platformio_env_vars())
        return env

    def _platformio_cmd(self) -> list[str] | None:
        runtime = resolve_platformio_runtime(self._workspace.root)
        if isinstance(runtime, Err):
            self._console.error("platformio: missing")
            if runtime.error.hint:
                self._console.print(f"hint: {runtime.error.hint}", Style.DIM)
            return None
        return runtime.value.command()

    def _read_app_config(self, app_path: Path) -> Result[AppConfig, BuildError]:
        app_cmake = app_path / "app.cmake"
        if not app_cmake.exists():
            return Err(AppConfigInvalid(path=app_cmake, reason="file not found"))

        content = app_cmake.read_text(encoding="utf-8")
        app_id = extract_cmake_var(content, "APP_ID")
        exe_name = extract_cmake_var(content, "APP_EXE_NAME")
        if not app_id or not exe_name:
            return Err(AppConfigInvalid(path=app_cmake, reason="missing APP_ID or APP_EXE_NAME"))
        return Ok(AppConfig(app_id=app_id, exe_name=exe_name))

    def _check_build_prereqs(self, *, dry_run: bool) -> Result[None, BuildError]:
        if not (self._workspace.midi_studio_dir / "core").is_dir():
            return Err(PrereqMissing(name="midi-studio/core", hint="Run: uv run ms sync --repos"))
        if not self._workspace.open_control_dir.is_dir():
            return Err(PrereqMissing(name="open-control", hint="Run: uv run ms sync --repos"))
        if not self._core_sdl_dir().is_dir():
            return Err(PrereqMissing(name="SDL build system", hint=str(self._core_sdl_dir())))

        core_dir = self._workspace.midi_studio_dir / "core"
        libdeps = core_dir / ".pio" / "libdeps"
        if libdeps.is_dir():
            return Ok(None)

        pio = self._platformio_cmd()
        if pio is None:
            return Err(ToolMissing(tool_id="platformio"))

        cmd = [*pio, "pkg", "install"]
        self._console.print(" ".join(cmd), Style.DIM)
        if dry_run:
            return Ok(None)

        result = run_silent(
            cmd,
            cwd=core_dir,
            env=self._base_env(),
            timeout=_PLATFORMIO_DEPS_TIMEOUT_SECONDS,
        )
        if isinstance(result, Err):
            return Err(PrereqMissing(name="PlatformIO libdeps", hint="pio pkg install failed"))
        return Ok(None)

    def _get_tool_path(self, tool_id: str) -> Result[Path, BuildError]:
        path = self._registry.get_bin_path(tool_id)
        if path is not None and path.exists():
            return Ok(path)

        found = shutil.which(tool_id)
        if found:
            return Ok(Path(found))

        return Err(ToolMissing(tool_id=tool_id))

    def _check_windows_native_prereqs(self) -> Result[None, BuildError]:
        sdl2_lib = self._registry.get_sdl2_lib()
        if sdl2_lib is None or not sdl2_lib.exists():
            return Err(PrereqMissing(name="SDL2", hint="Run: uv run ms sync --tools"))

        required = ("zig-cc", "zig-cxx", "zig-ar", "zig-ranlib")
        for name in required:
            path = self._registry.get_zig_wrapper(name)
            if path is None or not path.exists():
                return Err(
                    PrereqMissing(
                        name=f"Zig wrapper missing: {name}",
                        hint="Run: uv run ms sync --tools",
                    )
                )

        return Ok(None)

    def _check_unix_native_prereqs(self) -> Result[None, BuildError]:
        if shutil.which("c++") or shutil.which("g++") or shutil.which("clang++"):
            return Ok(None)

        hints = load_hints()
        platform_key = get_platform_key(self._platform.platform, self._platform.distro)
        hint = hints.get_tool_hint("g++", platform_key) or "Install a C++ compiler (g++/clang++)."
        return Err(PrereqMissing(name="C++ compiler", hint=hint))

    def _get_emcmake_path(self) -> Result[Path, BuildError]:
        emcmake = self._registry.get_emcmake()
        if emcmake is not None and emcmake.exists():
            return Ok(emcmake)
        return Err(ToolMissing(tool_id="emscripten", hint="emcmake not found"))

    def _print_build_error(self, error: BuildError) -> None:
        print_build_error(error, self._console)

    def _error_to_exit_code(self, error: BuildError) -> int:
        return build_error_exit_code(error)
