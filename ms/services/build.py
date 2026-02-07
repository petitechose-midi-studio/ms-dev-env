"""Build service for native and WASM targets.

Provides build orchestration using Ninja generator on all platforms:
- Windows: Zig compiler via zig-toolchain.cmake
- Linux/macOS: System compiler (GCC/Clang)
- WASM: Emscripten via emcmake
"""

from __future__ import annotations

import os
import re
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from ..core.app import resolve
from ..core.config import CONTROLLER_CORE_NATIVE_PORT, Config
from ..core.errors import ErrorCode
from ..core.result import Err, Ok, Result
from ..output.console import Style
from ..output.errors import build_error_exit_code, print_build_error
from ..platform.process import run_silent
from .base import BaseService
from .bridge_headless import spec_for, start_headless_bridge
from .build_errors import (
    AppConfigInvalid,
    AppNotFound,
    BuildError,
    CompileFailed,
    ConfigureFailed,
    OutputMissing,
    PrereqMissing,
    SdlAppNotFound,
    ToolMissing,
)
from .checkers.common import get_platform_key, load_hints

_CONFIGURE_TIMEOUT_SECONDS = 20 * 60.0
_COMPILE_TIMEOUT_SECONDS = 30 * 60.0
_PLATFORMIO_DEPS_TIMEOUT_SECONDS = 15 * 60.0


Target = Literal["native", "wasm"]


# -----------------------------------------------------------------------------
# App Config
# -----------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class AppConfig:
    app_id: str
    exe_name: str


class BuildService(BaseService):
    """Build service for native and WASM targets."""

    def build_native(self, *, app_name: str, dry_run: bool = False) -> Result[Path, BuildError]:
        """Build native executable for current platform.

        Returns:
            Ok(path) with path to built executable
            Err(BuildError) on failure
        """
        # Resolve app_name
        res = resolve(app_name, self._workspace.root)
        if isinstance(res, Err):
            return Err(
                AppNotFound(
                    name=res.error.name,
                    available=res.error.available,
                )
            )

        cb = res.value
        if cb.sdl_path is None:
            return Err(SdlAppNotFound(app_name=app_name))

        # Read app config
        app_cfg_result = self._read_app_config(cb.sdl_path)
        if isinstance(app_cfg_result, Err):
            return app_cfg_result
        app_cfg = app_cfg_result.value

        # Check prerequisites
        prereq_result = self._check_build_prereqs(dry_run=dry_run)
        if isinstance(prereq_result, Err):
            return prereq_result

        # Get tool paths
        cmake = self._get_tool_path("cmake")
        if isinstance(cmake, Err):
            return cmake
        ninja = self._get_tool_path("ninja")
        if isinstance(ninja, Err):
            return ninja

        # Windows-specific prereqs
        if self._platform.platform.is_windows:
            win_prereq = self._check_windows_native_prereqs()
            if isinstance(win_prereq, Err):
                return win_prereq

        # Unix-specific prereqs (Linux/macOS)
        if self._platform.platform.is_unix:
            unix_prereq = self._check_unix_native_prereqs()
            if isinstance(unix_prereq, Err):
                return unix_prereq

        # Setup build
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
            # Pre-set to avoid GNUInstallDirs warning in dependencies
            "-DCMAKE_INSTALL_LIBDIR=lib",
        ]

        # Platform-specific additions
        if self._platform.platform.is_windows:
            toolchain_file = self._core_sdl_dir() / "zig-toolchain.cmake"
            zig_ranlib = self._registry.get_zig_wrapper("zig-ranlib")
            configure_args += [
                f"-DCMAKE_TOOLCHAIN_FILE={toolchain_file}",
                f"-DTOOLS_DIR={self._registry.tools_dir}",
                # Avoid relying on a POSIX `true` placeholder on Windows.
                # (Some environments don't have a `true.exe` on PATH,
                # but cmd.exe still runs the rule.)
                f"-DCMAKE_RANLIB:FILEPATH={zig_ranlib}" if zig_ranlib else "",
                f"-DCMAKE_C_COMPILER_RANLIB:FILEPATH={zig_ranlib}" if zig_ranlib else "",
                f"-DCMAKE_CXX_COMPILER_RANLIB:FILEPATH={zig_ranlib}" if zig_ranlib else "",
            ]

            # Drop empty args if zig_ranlib was missing
            configure_args = [x for x in configure_args if x]

        build_args = [str(ninja.value), "-C", str(build_dir)]

        # Configure
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

        # Build
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

        # Verify output
        out_dir = self._workspace.bin_dir / app_cfg.app_id / "native"
        out_exe = out_dir / self._platform.platform.exe_name(app_cfg.exe_name)
        if not dry_run and not out_exe.exists():
            return Err(OutputMissing(path=out_exe))

        # Copy SDL2.dll on Windows
        if not dry_run and self._platform.platform.is_windows:
            sdl2_dll = self._registry.get_sdl2_dll()
            if sdl2_dll is not None and sdl2_dll.exists() and not (out_dir / "SDL2.dll").exists():
                shutil.copy2(sdl2_dll, out_dir / "SDL2.dll")

        return Ok(out_exe)

    def run_native(self, *, app_name: str) -> int:
        """Build and run native executable."""
        result = self.build_native(app_name=app_name)

        match result:
            case Ok(exe_path):
                cfg = self._config or Config()
                bridge = start_headless_bridge(
                    workspace=self._workspace,
                    platform=self._platform,
                    config=cfg,
                    console=self._console,
                    app_name=app_name,
                    mode="native",
                )
                if isinstance(bridge, Err):
                    self._console.error(bridge.error.message)
                    if bridge.error.hint:
                        self._console.print(f"hint: {bridge.error.hint}", Style.DIM)
                    return int(ErrorCode.ENV_ERROR)

                with bridge.value:
                    self._console.print(f"run: {exe_path}", Style.DIM)
                    args = [
                        str(exe_path),
                        "1053",
                        "--bridge-udp-port",
                        str(bridge.value.spec.controller_port),
                    ]
                    try:
                        run_result = run_silent(args, cwd=self._workspace.root, timeout=None)
                    except KeyboardInterrupt:
                        return 0

                    match run_result:
                        case Ok(_):
                            return 0
                        case Err(e):
                            return e.returncode
            case Err(error):
                self._print_build_error(error)
                return self._error_to_exit_code(error)

        # Defensive fallback for static analyzers / unexpected result variants.
        return 1

    def build_wasm(self, *, app_name: str, dry_run: bool = False) -> Result[Path, BuildError]:
        """Build WebAssembly target using Emscripten.

        Returns:
            Ok(path) with path to built HTML file
            Err(BuildError) on failure
        """
        # Resolve app_name
        res = resolve(app_name, self._workspace.root)
        if isinstance(res, Err):
            return Err(
                AppNotFound(
                    name=res.error.name,
                    available=res.error.available,
                )
            )

        cb = res.value
        if cb.sdl_path is None:
            return Err(SdlAppNotFound(app_name=app_name))

        # Read app config
        app_cfg_result = self._read_app_config(cb.sdl_path)
        if isinstance(app_cfg_result, Err):
            return app_cfg_result
        app_cfg = app_cfg_result.value

        # Check prerequisites
        prereq_result = self._check_build_prereqs(dry_run=dry_run)
        if isinstance(prereq_result, Err):
            return prereq_result

        # Get tool paths
        cmake = self._get_tool_path("cmake")
        if isinstance(cmake, Err):
            return cmake
        ninja = self._get_tool_path("ninja")
        if isinstance(ninja, Err):
            return ninja
        emcmake = self._get_emcmake_path()
        if isinstance(emcmake, Err):
            return emcmake

        # Setup build
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

        # Configure
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

            # Build
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

        # Verify output
        out_html = self._workspace.bin_dir / app_cfg.app_id / "wasm" / f"{app_cfg.exe_name}.html"
        if not dry_run and not out_html.exists():
            return Err(OutputMissing(path=out_html))

        return Ok(out_html)

    def serve_wasm(self, *, app_name: str, port: int = CONTROLLER_CORE_NATIVE_PORT) -> int:
        """Build WASM and serve via HTTP."""
        result = self.build_wasm(app_name=app_name)

        match result:
            case Ok(html_path):
                cfg = self._config or Config()
                # Compute expected WS port to avoid HTTP/WS collision on the same TCP port.
                expected_ws_port = spec_for(cfg, app_name=app_name, mode="wasm").controller_port
                if int(port) == int(expected_ws_port):
                    self._console.error(
                        f"HTTP port {port} conflicts with bridge WS port {expected_ws_port}"
                    )
                    return int(ErrorCode.USER_ERROR)

                bridge = start_headless_bridge(
                    workspace=self._workspace,
                    platform=self._platform,
                    config=cfg,
                    console=self._console,
                    app_name=app_name,
                    mode="wasm",
                )
                if isinstance(bridge, Err):
                    self._console.error(bridge.error.message)
                    if bridge.error.hint:
                        self._console.print(f"hint: {bridge.error.hint}", Style.DIM)
                    return int(ErrorCode.ENV_ERROR)

                out_dir = html_path.parent
                url_path = html_path.name
                ws_port = bridge.value.spec.controller_port
                self._console.print(
                    f"serve: http://localhost:{port}/{url_path}?bridgeWsPort={ws_port}",
                    Style.INFO,
                )

                with bridge.value:
                    cmd = [sys.executable, "-m", "http.server", str(port), "-d", str(out_dir)]
                    try:
                        run_result = run_silent(cmd, cwd=self._workspace.root, timeout=None)
                    except KeyboardInterrupt:
                        return 0
                    match run_result:
                        case Ok(_):
                            return 0
                        case Err(e):
                            return e.returncode
            case Err(error):
                self._print_build_error(error)
                return self._error_to_exit_code(error)

        # Defensive fallback for static analyzers / unexpected result variants.
        return 1

    # -------------------------------------------------------------------------
    # Internal helpers
    # -------------------------------------------------------------------------

    def _core_sdl_dir(self) -> Path:
        return self._workspace.midi_studio_dir / "core" / "sdl"

    def _base_env(self) -> dict[str, str]:
        env = os.environ.copy()
        env.update(self._registry.get_env_vars())
        env.update(self._workspace.platformio_env_vars())
        return env

    def _pio_cmd(self) -> Path | None:
        name = "pio.cmd" if self._platform.platform.is_windows else "pio"
        wrapper = self._workspace.tools_bin_dir / name
        if wrapper.exists():
            return wrapper

        pio = self._registry.get_bin_path("platformio")
        if pio is not None and pio.exists():
            return pio

        self._console.error("platformio: missing")
        self._console.print("hint: Run: uv run ms sync --tools", Style.DIM)
        return None

    def _read_app_config(self, app_path: Path) -> Result[AppConfig, BuildError]:
        """Read app.cmake and return AppConfig or error."""
        app_cmake = app_path / "app.cmake"
        if not app_cmake.exists():
            return Err(AppConfigInvalid(path=app_cmake, reason="file not found"))

        content = app_cmake.read_text(encoding="utf-8")
        app_id = _extract_cmake_var(content, "APP_ID")
        exe_name = _extract_cmake_var(content, "APP_EXE_NAME")
        if not app_id or not exe_name:
            return Err(AppConfigInvalid(path=app_cmake, reason="missing APP_ID or APP_EXE_NAME"))
        return Ok(AppConfig(app_id=app_id, exe_name=exe_name))

    def _check_build_prereqs(self, *, dry_run: bool) -> Result[None, BuildError]:
        """Check core layout and PIO libdeps."""
        # Check core layout
        if not (self._workspace.midi_studio_dir / "core").is_dir():
            return Err(PrereqMissing(name="midi-studio/core", hint="Run: uv run ms sync --repos"))
        if not self._workspace.open_control_dir.is_dir():
            return Err(PrereqMissing(name="open-control", hint="Run: uv run ms sync --repos"))
        if not self._core_sdl_dir().is_dir():
            return Err(PrereqMissing(name="SDL build system", hint=str(self._core_sdl_dir())))

        # Check PIO libdeps
        core_dir = self._workspace.midi_studio_dir / "core"
        libdeps = core_dir / ".pio" / "libdeps"
        if libdeps.is_dir():
            return Ok(None)

        pio = self._pio_cmd()
        if pio is None:
            return Err(ToolMissing(tool_id="platformio"))

        cmd = [str(pio), "pkg", "install"]
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
        """Get tool path or error."""
        p = self._registry.get_bin_path(tool_id)
        if p is not None and p.exists():
            return Ok(p)
        found = shutil.which(tool_id)
        if found:
            return Ok(Path(found))
        return Err(ToolMissing(tool_id=tool_id))

    def _check_windows_native_prereqs(self) -> Result[None, BuildError]:
        """Check Windows native build prerequisites."""
        # Check SDL2 MinGW package
        sdl2_lib = self._registry.get_sdl2_lib()
        if sdl2_lib is None or not sdl2_lib.exists():
            return Err(PrereqMissing(name="SDL2", hint="Run: uv run ms sync --tools"))

        # Check Zig wrappers
        required = ("zig-cc", "zig-cxx", "zig-ar", "zig-ranlib")
        for name in required:
            p = self._registry.get_zig_wrapper(name)
            if p is None or not p.exists():
                return Err(
                    PrereqMissing(
                        name=f"Zig wrapper missing: {name}",
                        hint="Run: uv run ms sync --tools",
                    )
                )

        return Ok(None)

    def _check_unix_native_prereqs(self) -> Result[None, BuildError]:
        """Check Linux/macOS native build prerequisites."""

        # CMake projects here are C++-heavy; give a clear error before configure.
        if shutil.which("c++") or shutil.which("g++") or shutil.which("clang++"):
            return Ok(None)

        hints = load_hints()
        platform_key = get_platform_key(self._platform.platform, self._platform.distro)
        hint = hints.get_tool_hint("g++", platform_key) or "Install a C++ compiler (g++/clang++)."
        return Err(PrereqMissing(name="C++ compiler", hint=hint))

    def _get_emcmake_path(self) -> Result[Path, BuildError]:
        """Get emcmake.py path or error."""
        emcmake = self._registry.get_emcmake()
        if emcmake is not None and emcmake.exists():
            return Ok(emcmake)
        return Err(ToolMissing(tool_id="emscripten", hint="emcmake not found"))

    def _print_build_error(self, error: BuildError) -> None:
        """Print build error to console."""
        print_build_error(error, self._console)

    def _error_to_exit_code(self, error: BuildError) -> int:
        """Convert BuildError to exit code."""
        return build_error_exit_code(error)


_CMAKE_SET_RE = re.compile(r"^\s*set\(\s*(?P<name>[A-Z0-9_]+)\s+\"(?P<value>[^\"]+)\"\s*\)\s*$")


def _extract_cmake_var(content: str, name: str) -> str | None:
    for line in content.splitlines():
        m = _CMAKE_SET_RE.match(line)
        if not m:
            continue
        if m.group("name") == name:
            return m.group("value")
    return None
