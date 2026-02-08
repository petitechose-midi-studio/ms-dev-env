from __future__ import annotations

import shutil
import sys
from pathlib import Path

from ms.core.app import resolve
from ms.core.result import Err, Ok, Result
from ms.output.console import Style
from ms.platform.process import run_silent
from ms.services.build_errors import (
    AppNotFound,
    BuildError,
    CompileFailed,
    ConfigureFailed,
    OutputMissing,
    SdlAppNotFound,
)

from .helpers import BuildHelpersMixin

_CONFIGURE_TIMEOUT_SECONDS = 20 * 60.0
_COMPILE_TIMEOUT_SECONDS = 30 * 60.0


class BuildTargetsMixin(BuildHelpersMixin):
    def build_native(self, *, app_name: str, dry_run: bool = False) -> Result[Path, BuildError]:
        res = resolve(app_name, self._workspace.root)
        if isinstance(res, Err):
            return Err(AppNotFound(name=res.error.name, available=res.error.available))

        cb = res.value
        if cb.sdl_path is None:
            return Err(SdlAppNotFound(app_name=app_name))

        app_cfg_result = self._read_app_config(cb.sdl_path)
        if isinstance(app_cfg_result, Err):
            return app_cfg_result
        app_cfg = app_cfg_result.value

        prereq_result = self._check_build_prereqs(dry_run=dry_run)
        if isinstance(prereq_result, Err):
            return prereq_result

        cmake = self._get_tool_path("cmake")
        if isinstance(cmake, Err):
            return cmake
        ninja = self._get_tool_path("ninja")
        if isinstance(ninja, Err):
            return ninja

        if self._platform.platform.is_windows:
            win_prereq = self._check_windows_native_prereqs()
            if isinstance(win_prereq, Err):
                return win_prereq

        if self._platform.platform.is_unix:
            unix_prereq = self._check_unix_native_prereqs()
            if isinstance(unix_prereq, Err):
                return unix_prereq

        sdl_src = self._core_sdl_dir()
        build_dir = self._workspace.build_dir / app_cfg.app_id / "native"
        build_dir.mkdir(parents=True, exist_ok=True)
        env = self._base_env()

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

        if self._platform.platform.is_windows:
            toolchain_file = self._core_sdl_dir() / "zig-toolchain.cmake"
            zig_ranlib = self._registry.get_zig_wrapper("zig-ranlib")
            configure_args += [
                f"-DCMAKE_TOOLCHAIN_FILE={toolchain_file}",
                f"-DTOOLS_DIR={self._registry.tools_dir}",
                f"-DCMAKE_RANLIB:FILEPATH={zig_ranlib}" if zig_ranlib else "",
                f"-DCMAKE_C_COMPILER_RANLIB:FILEPATH={zig_ranlib}" if zig_ranlib else "",
                f"-DCMAKE_CXX_COMPILER_RANLIB:FILEPATH={zig_ranlib}" if zig_ranlib else "",
            ]
            configure_args = [arg for arg in configure_args if arg]

        build_args = [str(ninja.value), "-C", str(build_dir)]

        self._console.print(" ".join(configure_args), Style.DIM)
        if not dry_run:
            result = run_silent(
                configure_args,
                cwd=self._workspace.root,
                env=env,
                timeout=_CONFIGURE_TIMEOUT_SECONDS,
            )
            if isinstance(result, Err):
                return Err(ConfigureFailed(returncode=result.error.returncode))

        self._console.print(" ".join(build_args), Style.DIM)
        if not dry_run:
            result = run_silent(
                build_args,
                cwd=self._workspace.root,
                env=env,
                timeout=_COMPILE_TIMEOUT_SECONDS,
            )
            if isinstance(result, Err):
                return Err(CompileFailed(returncode=result.error.returncode))

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

        app_cfg_result = self._read_app_config(cb.sdl_path)
        if isinstance(app_cfg_result, Err):
            return app_cfg_result
        app_cfg = app_cfg_result.value

        prereq_result = self._check_build_prereqs(dry_run=dry_run)
        if isinstance(prereq_result, Err):
            return prereq_result

        cmake = self._get_tool_path("cmake")
        if isinstance(cmake, Err):
            return cmake
        ninja = self._get_tool_path("ninja")
        if isinstance(ninja, Err):
            return ninja
        emcmake = self._get_emcmake_path()
        if isinstance(emcmake, Err):
            return emcmake

        sdl_src = self._core_sdl_dir()
        build_dir = self._workspace.build_dir / app_cfg.app_id / "wasm"
        build_dir.mkdir(parents=True, exist_ok=True)

        env = self._base_env()
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

        self._console.print(" ".join(str(x) for x in configure_args), Style.DIM)
        if not dry_run:
            result = run_silent(
                configure_args,
                cwd=self._workspace.root,
                env=env,
                timeout=_CONFIGURE_TIMEOUT_SECONDS,
            )
            if isinstance(result, Err):
                return Err(ConfigureFailed(returncode=result.error.returncode))

            build_cmd = [str(ninja.value), "-C", str(build_dir)]
            self._console.print(" ".join(build_cmd), Style.DIM)
            result = run_silent(
                build_cmd,
                cwd=self._workspace.root,
                env=env,
                timeout=_COMPILE_TIMEOUT_SECONDS,
            )
            if isinstance(result, Err):
                return Err(CompileFailed(returncode=result.error.returncode))

        out_html = self._workspace.bin_dir / app_cfg.app_id / "wasm" / f"{app_cfg.exe_name}.html"
        if not dry_run and not out_html.exists():
            return Err(OutputMissing(path=out_html))

        return Ok(out_html)
