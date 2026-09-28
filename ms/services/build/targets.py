from __future__ import annotations

import shutil
import sys
from pathlib import Path

from ms.core.app import resolve
from ms.core.result import Err, Ok, Result
from ms.core.workspace import Workspace
from ms.output.console import ConsoleProtocol, Style
from ms.platform.detection import PlatformInfo
from ms.platform.process import run_silent
from ms.platform.resources import parallel_jobs_warning, resolve_parallel_jobs
from ms.services.build_errors import (
    AppNotFound,
    BuildError,
    CompileFailed,
    ConfigureFailed,
    OutputMissing,
    PrereqMissing,
    SdlAppNotFound,
)
from ms.services.toolchain_env import base_env
from ms.tools.registry import ToolRegistry

from .helpers import BuildPrerequisites

_CONFIGURE_TIMEOUT_SECONDS = 20 * 60.0
_COMPILE_TIMEOUT_SECONDS = 30 * 60.0


class BuildTargets:
    """Configure and compile targets using an explicit prerequisite owner."""

    def __init__(
        self,
        *,
        workspace: Workspace,
        platform: PlatformInfo,
        console: ConsoleProtocol,
        registry: ToolRegistry,
    ) -> None:
        self._workspace = workspace
        self._platform = platform
        self._console = console
        self._registry = registry
        self._prerequisites = BuildPrerequisites(
            workspace=workspace,
            platform=platform,
            console=console,
            registry=registry,
        )

    def build_core_file_tool(self, *, dry_run: bool = False) -> Result[Path, BuildError]:
        core_dir = self._workspace.midi_studio_dir / "core"
        prerequisites = (
            ("midi-studio/core", core_dir),
            ("open-control", self._workspace.open_control_dir),
            ("midi-studio/device-support", self._workspace.midi_studio_dir / "device-support"),
        )
        for name, path in prerequisites:
            if not path.is_dir():
                return Err(PrereqMissing(name=name, hint="Run: uv run ms sync --repos"))

        cmake = self._prerequisites.get_tool_path("cmake")
        if isinstance(cmake, Err):
            return cmake
        ninja = self._prerequisites.get_tool_path("ninja")
        if isinstance(ninja, Err):
            return ninja

        if self._platform.platform.is_windows:
            win_prereq = self._prerequisites.check_windows_native_prereqs(require_sdl2=False)
            if isinstance(win_prereq, Err):
                return win_prereq
        if self._platform.platform.is_unix:
            unix_prereq = self._prerequisites.check_unix_native_prereqs()
            if isinstance(unix_prereq, Err):
                return unix_prereq

        build_dir = core_dir / "build" / "core-native"
        build_dir.mkdir(parents=True, exist_ok=True)
        env = base_env(registry=self._registry, workspace=self._workspace)
        configure_args = [
            str(cmake.value),
            "-G",
            "Ninja",
            "-S",
            str(core_dir),
            "-B",
            str(build_dir),
            f"-DMS_CORE_OPEN_CONTROL_ROOT={self._workspace.open_control_dir}",
            f"-DMS_DEVICE_SUPPORT_DIR={self._workspace.midi_studio_dir / 'device-support'}",
            "-DMS_CORE_BUILD_TESTS=OFF",
            "-DCMAKE_BUILD_TYPE=Release",
            f"-DCMAKE_MAKE_PROGRAM={ninja.value}",
        ]
        if self._platform.platform.is_windows:
            configure_args += self._prerequisites.windows_zig_cmake_args()
            configure_args = [arg for arg in configure_args if arg]

        build_args = [str(ninja.value), "-C", str(build_dir), "ms-core-file-tool"]
        if self._platform.platform.is_windows:
            selection = resolve_parallel_jobs(jobs_env_var="MS_WINDOWS_NATIVE_JOBS")
            warning = parallel_jobs_warning(
                selection=selection,
                jobs_env_var="MS_WINDOWS_NATIVE_JOBS",
            )
            if warning is not None:
                self._console.warning(warning)
            build_args += ["-j", str(selection.jobs)]

        self._console.print(" ".join(configure_args), Style.DIM)
        if not dry_run:
            result = run_silent(
                configure_args,
                cwd=self._workspace.root,
                env=env,
                timeout=_CONFIGURE_TIMEOUT_SECONDS,
            )
            if isinstance(result, Err):
                return Err(
                    ConfigureFailed(
                        returncode=result.error.returncode,
                        details=result.error.stderr,
                    )
                )

        self._console.print(" ".join(build_args), Style.DIM)
        if not dry_run:
            result = run_silent(
                build_args,
                cwd=self._workspace.root,
                env=env,
                timeout=_COMPILE_TIMEOUT_SECONDS,
            )
            if isinstance(result, Err):
                return Err(
                    CompileFailed(
                        returncode=result.error.returncode,
                        details=result.error.stderr,
                    )
                )

        out_exe = build_dir / self._platform.platform.exe_name("ms-core-file-tool")
        if not dry_run and not out_exe.exists():
            return Err(OutputMissing(path=out_exe))
        return Ok(out_exe)

    def build_native(self, *, app_name: str, dry_run: bool = False) -> Result[Path, BuildError]:
        res = resolve(app_name, self._workspace.root)
        if isinstance(res, Err):
            return Err(AppNotFound(name=res.error.name, available=res.error.available))

        cb = res.value
        if cb.sdl_path is None:
            return Err(SdlAppNotFound(app_name=app_name))

        app_cfg_result = self._prerequisites.read_app_config(cb.sdl_path)
        if isinstance(app_cfg_result, Err):
            return app_cfg_result
        app_cfg = app_cfg_result.value

        prereq_result = self._prerequisites.check_build_prereqs(dry_run=dry_run)
        if isinstance(prereq_result, Err):
            return prereq_result

        cmake = self._prerequisites.get_tool_path("cmake")
        if isinstance(cmake, Err):
            return cmake
        ninja = self._prerequisites.get_tool_path("ninja")
        if isinstance(ninja, Err):
            return ninja

        if self._platform.platform.is_windows:
            win_prereq = self._prerequisites.check_windows_native_prereqs()
            if isinstance(win_prereq, Err):
                return win_prereq

        if self._platform.platform.is_unix:
            unix_prereq = self._prerequisites.check_unix_native_prereqs()
            if isinstance(unix_prereq, Err):
                return unix_prereq

        sdl_src = self._workspace.midi_studio_dir / "core" / "sdl"
        build_dir = self._workspace.build_dir / app_cfg.app_id / "native"
        build_dir.mkdir(parents=True, exist_ok=True)
        env = base_env(registry=self._registry, workspace=self._workspace)

        configure_args = [
            str(cmake.value),
            "-G",
            "Ninja",
            "-S",
            str(sdl_src),
            "-B",
            str(build_dir),
            f"-DAPP_PATH={cb.sdl_path}",
            f"-DBIN_OUTPUT_DIR={self._workspace.bin_dir}",
            "-DCMAKE_BUILD_TYPE=Release",
            f"-DCMAKE_MAKE_PROGRAM={ninja.value}",
            "-DCMAKE_INSTALL_LIBDIR=lib",
        ]
        configure_args += self._prerequisites.sdl_dependency_cmake_args()

        if self._platform.platform.is_windows:
            configure_args += self._prerequisites.windows_zig_cmake_args()
            configure_args = [arg for arg in configure_args if arg]

        build_args = [str(ninja.value), "-C", str(build_dir)]

        # Default to the fastest CPU-only heuristic on Windows. Developers can
        # still override the job count explicitly from their shell.
        if self._platform.platform.is_windows:
            selection = resolve_parallel_jobs(jobs_env_var="MS_WINDOWS_NATIVE_JOBS")
            warning = parallel_jobs_warning(
                selection=selection,
                jobs_env_var="MS_WINDOWS_NATIVE_JOBS",
            )
            if warning is not None:
                self._console.warning(warning)
            build_args += ["-j", str(selection.jobs)]

        self._console.print(" ".join(configure_args), Style.DIM)
        if not dry_run:
            result = run_silent(
                configure_args,
                cwd=self._workspace.root,
                env=env,
                timeout=_CONFIGURE_TIMEOUT_SECONDS,
            )
            if isinstance(result, Err):
                return Err(
                    ConfigureFailed(
                        returncode=result.error.returncode,
                        details=result.error.stderr,
                    )
                )

        self._console.print(" ".join(build_args), Style.DIM)
        if not dry_run:
            result = run_silent(
                build_args,
                cwd=self._workspace.root,
                env=env,
                timeout=_COMPILE_TIMEOUT_SECONDS,
            )
            if isinstance(result, Err):
                return Err(
                    CompileFailed(
                        returncode=result.error.returncode,
                        details=result.error.stderr,
                    )
                )

        out_dir = self._workspace.bin_dir / app_cfg.app_id / "native"
        out_exe = out_dir / self._platform.platform.exe_name(app_cfg.exe_name)
        if not dry_run and not out_exe.exists():
            return Err(OutputMissing(path=out_exe))

        if not dry_run and self._platform.platform.is_windows:
            sdl2_dll = self._registry.get_sdl2_dll()
            if sdl2_dll is not None and sdl2_dll.exists() and not (out_dir / "SDL2.dll").exists():
                shutil.copy2(sdl2_dll, out_dir / "SDL2.dll")

        return Ok(out_exe)

    def build_wasm(self, *, app_name: str, dry_run: bool = False) -> Result[Path, BuildError]:
        res = resolve(app_name, self._workspace.root)
        if isinstance(res, Err):
            return Err(AppNotFound(name=res.error.name, available=res.error.available))

        cb = res.value
        if cb.sdl_path is None:
            return Err(SdlAppNotFound(app_name=app_name))

        app_cfg_result = self._prerequisites.read_app_config(cb.sdl_path)
        if isinstance(app_cfg_result, Err):
            return app_cfg_result
        app_cfg = app_cfg_result.value

        prereq_result = self._prerequisites.check_build_prereqs(dry_run=dry_run)
        if isinstance(prereq_result, Err):
            return prereq_result

        cmake = self._prerequisites.get_tool_path("cmake")
        if isinstance(cmake, Err):
            return cmake
        ninja = self._prerequisites.get_tool_path("ninja")
        if isinstance(ninja, Err):
            return ninja
        emcmake = self._prerequisites.get_emcmake_path()
        if isinstance(emcmake, Err):
            return emcmake

        sdl_src = self._workspace.midi_studio_dir / "core" / "sdl"
        build_dir = self._workspace.build_dir / app_cfg.app_id / "wasm"
        build_dir.mkdir(parents=True, exist_ok=True)

        env = base_env(registry=self._registry, workspace=self._workspace)
        em_config = self._registry.get_em_config()
        if em_config is not None:
            env["EM_CONFIG"] = str(em_config)
        env.setdefault("EMSDK_PYTHON", sys.executable)

        configure_args = [
            sys.executable,
            str(emcmake.value),
            str(cmake.value),
            "-G",
            "Ninja",
            "-S",
            str(sdl_src),
            "-B",
            str(build_dir),
            f"-DAPP_PATH={cb.sdl_path}",
            f"-DBIN_OUTPUT_DIR={self._workspace.bin_dir}",
            "-DCMAKE_BUILD_TYPE=Release",
            f"-DCMAKE_MAKE_PROGRAM={ninja.value}",
        ]
        configure_args += self._prerequisites.sdl_dependency_cmake_args()

        self._console.print(" ".join(str(x) for x in configure_args), Style.DIM)
        if not dry_run:
            result = run_silent(
                configure_args,
                cwd=self._workspace.root,
                env=env,
                timeout=_CONFIGURE_TIMEOUT_SECONDS,
            )
            if isinstance(result, Err):
                return Err(
                    ConfigureFailed(
                        returncode=result.error.returncode,
                        details=result.error.stderr,
                    )
                )

            build_cmd = [str(ninja.value), "-C", str(build_dir)]
            self._console.print(" ".join(build_cmd), Style.DIM)
            result = run_silent(
                build_cmd,
                cwd=self._workspace.root,
                env=env,
                timeout=_COMPILE_TIMEOUT_SECONDS,
            )
            if isinstance(result, Err):
                return Err(
                    CompileFailed(
                        returncode=result.error.returncode,
                        details=result.error.stderr,
                    )
                )

        out_html = self._workspace.bin_dir / app_cfg.app_id / "wasm" / f"{app_cfg.exe_name}.html"
        if not dry_run and not out_html.exists():
            return Err(OutputMissing(path=out_html))

        return Ok(out_html)
