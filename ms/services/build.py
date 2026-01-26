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
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from ms.core.app import AppError, resolve
from ms.core.config import Config
from ms.core.errors import ErrorCode
from ms.core.result import Err, Ok, Result
from ms.core.workspace import Workspace
from ms.output.console import ConsoleProtocol, Style
from ms.platform.detection import Platform, PlatformInfo
from ms.tools.registry import ToolRegistry


# -----------------------------------------------------------------------------
# Build Error Types
# -----------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class AppNotFound:
    """App does not exist."""

    name: str
    available: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class SdlAppNotFound:
    """SDL app not found for app."""

    app_name: str


@dataclass(frozen=True, slots=True)
class AppConfigInvalid:
    """App config (app.cmake) missing or invalid."""

    path: Path
    reason: str


@dataclass(frozen=True, slots=True)
class ToolMissing:
    """Required tool not installed."""

    tool_id: str
    hint: str = "Run: ms tools sync"


@dataclass(frozen=True, slots=True)
class PrereqMissing:
    """Build prerequisite missing."""

    name: str
    hint: str


@dataclass(frozen=True, slots=True)
class ConfigureFailed:
    """CMake configure step failed."""

    returncode: int


@dataclass(frozen=True, slots=True)
class CompileFailed:
    """Build/compile step failed."""

    returncode: int


@dataclass(frozen=True, slots=True)
class OutputMissing:
    """Expected output file not found."""

    path: Path


BuildError = (
    AppNotFound
    | SdlAppNotFound
    | AppConfigInvalid
    | ToolMissing
    | PrereqMissing
    | ConfigureFailed
    | CompileFailed
    | OutputMissing
)

Target = Literal["native", "wasm"]


# -----------------------------------------------------------------------------
# App Config
# -----------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class AppConfig:
    app_id: str
    exe_name: str


class BuildService:
    def __init__(
        self,
        *,
        workspace: Workspace,
        platform: PlatformInfo,
        config: Config | None,
        console: ConsoleProtocol,
    ) -> None:
        self._workspace = workspace
        self._platform = platform
        self._config = config
        self._console = console

        tools_dir = workspace.root / (config.paths.tools if config else "tools")
        self._registry = ToolRegistry(
            tools_dir=tools_dir,
            platform=platform.platform,
            arch=platform.arch,
        )

    def build_native(
        self, *, app_name: str, dry_run: bool = False
    ) -> Result[Path, BuildError]:
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
        app_cfg_result = self._read_app_config_result(cb.sdl_path)
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
        if self._platform.platform == Platform.WINDOWS:
            win_prereq = self._check_windows_native_prereqs()
            if isinstance(win_prereq, Err):
                return win_prereq

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
        ]

        # Platform-specific additions
        if self._platform.platform == Platform.WINDOWS:
            toolchain_file = self._core_sdl_dir() / "zig-toolchain.cmake"
            sdl2_root = self._registry.tools_dir / "sdl2"
            configure_args += [
                f"-DCMAKE_TOOLCHAIN_FILE={toolchain_file}",
                f"-DSDL2_ROOT={sdl2_root}",
            ]

        build_args = [str(ninja.value), "-C", str(build_dir)]

        # Configure
        self._console.print(" ".join(configure_args), Style.DIM)
        if not dry_run:
            proc = subprocess.run(
                configure_args, cwd=str(self._workspace.root), env=env, check=False
            )
            if proc.returncode != 0:
                return Err(ConfigureFailed(returncode=proc.returncode))

        # Build
        self._console.print(" ".join(build_args), Style.DIM)
        if not dry_run:
            proc = subprocess.run(
                build_args, cwd=str(self._workspace.root), env=env, check=False
            )
            if proc.returncode != 0:
                return Err(CompileFailed(returncode=proc.returncode))

        # Verify output
        out_dir = self._workspace.bin_dir / app_cfg.app_id / "native"
        out_exe = out_dir / self._platform.platform.exe_name(app_cfg.exe_name)
        if not dry_run and not out_exe.exists():
            return Err(OutputMissing(path=out_exe))

        # Copy SDL2.dll on Windows
        if not dry_run and self._platform.platform == Platform.WINDOWS:
            sdl2_dll = self._registry.tools_dir / "sdl2" / "bin" / "SDL2.dll"
            if sdl2_dll.exists() and not (out_dir / "SDL2.dll").exists():
                shutil.copy2(sdl2_dll, out_dir / "SDL2.dll")

        return Ok(out_exe)

    def run_native(self, *, app_name: str) -> int:
        """Build and run native executable."""
        result = self.build_native(app_name=app_name)

        match result:
            case Ok(exe_path):
                self._console.print(f"run: {exe_path}", Style.DIM)
                return subprocess.run(
                    [str(exe_path)], cwd=str(self._workspace.root), check=False
                ).returncode
            case Err(error):
                self._print_build_error(error)
                return self._error_to_exit_code(error)

    def build_wasm(
        self, *, app_name: str, dry_run: bool = False
    ) -> Result[Path, BuildError]:
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
        app_cfg_result = self._read_app_config_result(cb.sdl_path)
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
        env["EM_CONFIG"] = str(self._registry.tools_dir / "emsdk" / ".emscripten")
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
            proc = subprocess.run(
                configure_args, cwd=str(self._workspace.root), env=env, check=False
            )
            if proc.returncode != 0:
                return Err(ConfigureFailed(returncode=proc.returncode))

            # Build
            build_cmd = [str(ninja.value), "-C", str(build_dir)]
            self._console.print(" ".join(build_cmd), Style.DIM)
            proc = subprocess.run(
                build_cmd, cwd=str(self._workspace.root), env=env, check=False
            )
            if proc.returncode != 0:
                return Err(CompileFailed(returncode=proc.returncode))

        # Verify output
        out_html = self._workspace.bin_dir / app_cfg.app_id / "wasm" / f"{app_cfg.exe_name}.html"
        if not dry_run and not out_html.exists():
            return Err(OutputMissing(path=out_html))

        return Ok(out_html)

    def serve_wasm(self, *, app_name: str, port: int = 8000) -> int:
        """Build WASM and serve via HTTP."""
        result = self.build_wasm(app_name=app_name)

        match result:
            case Ok(html_path):
                out_dir = html_path.parent
                url_path = html_path.name
                self._console.print(f"serve: http://localhost:{port}/{url_path}", Style.INFO)

                cmd = [sys.executable, "-m", "http.server", str(port), "-d", str(out_dir)]
                return subprocess.run(cmd, cwd=str(self._workspace.root), check=False).returncode
            case Err(error):
                self._print_build_error(error)
                return self._error_to_exit_code(error)

    # -------------------------------------------------------------------------
    # Internal helpers
    # -------------------------------------------------------------------------

    def _core_sdl_dir(self) -> Path:
        return self._workspace.midi_studio_dir / "core" / "sdl"

    def _ensure_core_layout(self) -> bool:
        if not (self._workspace.midi_studio_dir / "core").is_dir():
            self._console.error("midi-studio/core is missing")
            self._console.print("hint: Run: uv run ms repos sync", Style.DIM)
            return False
        if not (self._workspace.open_control_dir).is_dir():
            self._console.error("open-control is missing")
            self._console.print("hint: Run: uv run ms repos sync", Style.DIM)
            return False
        if not self._core_sdl_dir().is_dir():
            self._console.error(f"SDL build system not found: {self._core_sdl_dir()}")
            return False
        return True

    def _ensure_pio_libdeps(self, *, dry_run: bool) -> bool:
        """Ensure PlatformIO libdeps are installed (provides LVGL)."""
        core_dir = self._workspace.midi_studio_dir / "core"
        libdeps = core_dir / ".pio" / "libdeps"
        if libdeps.is_dir():
            return True

        pio = self._pio_cmd()
        if pio is None:
            return False

        cmd = [str(pio), "pkg", "install"]
        self._console.print(" ".join(cmd), Style.DIM)
        if dry_run:
            return True

        proc = subprocess.run(cmd, cwd=str(core_dir), env=self._base_env(), check=False)
        if proc.returncode != 0:
            self._console.error("pio pkg install failed")
            return False
        return True

    def _ensure_windows_native_prereqs(self) -> bool:
        """Check Windows native build prerequisites (Zig, SDL2)."""
        # Check SDL2 MinGW package is installed
        sdl2_lib = self._registry.tools_dir / "sdl2" / "lib" / "libSDL2.dll.a"
        if not sdl2_lib.exists():
            self._console.error("SDL2 not found")
            self._console.print("hint: Run: uv run ms tools sync", Style.DIM)
            return False

        # Check Zig wrappers exist
        zig_cc = self._registry.tools_dir / "bin" / "zig-cc.cmd"
        if not zig_cc.exists():
            self._console.error("Zig compiler wrappers not found")
            self._console.print("hint: Run: uv run ms tools sync", Style.DIM)
            return False

        return True

    def _base_env(self) -> dict[str, str]:
        env = os.environ.copy()
        env.update(self._registry.get_env_vars())
        env.update(self._platformio_env_vars())
        return env

    def _platformio_env_vars(self) -> dict[str, str]:
        return {
            "PLATFORMIO_CORE_DIR": str(self._workspace.state_dir / "platformio"),
            "PLATFORMIO_CACHE_DIR": str(self._workspace.state_dir / "platformio-cache"),
            "PLATFORMIO_BUILD_CACHE_DIR": str(self._workspace.state_dir / "platformio-build-cache"),
        }

    def _tool_path(self, tool_id: str) -> Path | None:
        p = self._registry.get_bin_path(tool_id)
        if p is not None and p.exists():
            return p
        found = shutil.which(tool_id)
        if found:
            return Path(found)
        self._console.error(f"{tool_id}: missing")
        self._console.print("hint: Run: uv run ms tools sync", Style.DIM)
        return None

    def _pio_cmd(self) -> Path | None:
        name = "pio.cmd" if self._platform.platform == Platform.WINDOWS else "pio"
        wrapper = self._workspace.tools_bin_dir / name
        if wrapper.exists():
            return wrapper

        pio = self._registry.get_bin_path("platformio")
        if pio is not None and pio.exists():
            return pio

        self._console.error("platformio: missing")
        self._console.print("hint: Run: uv run ms tools sync", Style.DIM)
        return None

    def _emcmake_py(self) -> Path | None:
        emcmake = self._registry.tools_dir / "emsdk" / "upstream" / "emscripten" / "emcmake.py"
        if emcmake.exists():
            return emcmake
        self._console.error(f"emcmake.py not found: {emcmake}")
        self._console.print("hint: Run: uv run ms tools sync", Style.DIM)
        return None

    def _read_app_config(self, app_path: Path) -> AppConfig | None:
        app_cmake = app_path / "app.cmake"
        if not app_cmake.exists():
            self._console.error(f"app config not found: {app_cmake}")
            return None

        content = app_cmake.read_text(encoding="utf-8")
        app_id = _extract_cmake_var(content, "APP_ID")
        exe_name = _extract_cmake_var(content, "APP_EXE_NAME")
        if not app_id or not exe_name:
            self._console.error(f"invalid app config: {app_cmake}")
            return None
        return AppConfig(app_id=app_id, exe_name=exe_name)

    def _print_app_error(self, err: AppError) -> None:
        msg = err.message
        if err.available:
            msg += f"\nAvailable: {', '.join(err.available)}"
        self._console.error(msg)

    # -------------------------------------------------------------------------
    # Result-based helpers (for new API)
    # -------------------------------------------------------------------------

    def _read_app_config_result(self, app_path: Path) -> Result[AppConfig, BuildError]:
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
            return Err(PrereqMissing(name="midi-studio/core", hint="Run: ms repos sync"))
        if not self._workspace.open_control_dir.is_dir():
            return Err(PrereqMissing(name="open-control", hint="Run: ms repos sync"))
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

        proc = subprocess.run(cmd, cwd=str(core_dir), env=self._base_env(), check=False)
        if proc.returncode != 0:
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
        sdl2_lib = self._registry.tools_dir / "sdl2" / "lib" / "libSDL2.dll.a"
        if not sdl2_lib.exists():
            return Err(PrereqMissing(name="SDL2", hint="Run: ms tools sync"))

        # Check Zig wrappers
        zig_cc = self._registry.tools_dir / "bin" / "zig-cc.cmd"
        if not zig_cc.exists():
            return Err(PrereqMissing(name="Zig compiler wrappers", hint="Run: ms tools sync"))

        return Ok(None)

    def _get_emcmake_path(self) -> Result[Path, BuildError]:
        """Get emcmake.py path or error."""
        emcmake = self._registry.tools_dir / "emsdk" / "upstream" / "emscripten" / "emcmake.py"
        if emcmake.exists():
            return Ok(emcmake)
        return Err(ToolMissing(tool_id="emscripten", hint=f"emcmake.py not found: {emcmake}"))

    def _print_build_error(self, error: BuildError) -> None:
        """Print build error to console."""
        match error:
            case AppNotFound(name=name, available=available):
                self._console.error(f"Unknown app_name: {name}")
                if available:
                    self._console.print(f"Available: {', '.join(available)}", Style.DIM)
            case SdlAppNotFound(app_name=app_name):
                self._console.error(f"SDL app not found for app_name: {app_name}")
            case AppConfigInvalid(path=path, reason=reason):
                self._console.error(f"Invalid app config: {path} ({reason})")
            case ToolMissing(tool_id=tool_id, hint=hint):
                self._console.error(f"{tool_id}: missing")
                self._console.print(f"hint: {hint}", Style.DIM)
            case PrereqMissing(name=name, hint=hint):
                self._console.error(f"{name}: missing")
                self._console.print(f"hint: {hint}", Style.DIM)
            case ConfigureFailed(returncode=rc):
                self._console.error(f"cmake configure failed (exit {rc})")
            case CompileFailed(returncode=rc):
                self._console.error(f"build failed (exit {rc})")
            case OutputMissing(path=path):
                self._console.error(f"output not found: {path}")

    def _error_to_exit_code(self, error: BuildError) -> int:
        """Convert BuildError to exit code."""
        match error:
            case AppNotFound():
                return int(ErrorCode.USER_ERROR)
            case SdlAppNotFound() | AppConfigInvalid():
                return int(ErrorCode.ENV_ERROR)
            case ToolMissing() | PrereqMissing():
                return int(ErrorCode.ENV_ERROR)
            case ConfigureFailed() | CompileFailed():
                return int(ErrorCode.BUILD_ERROR)
            case OutputMissing():
                return int(ErrorCode.IO_ERROR)


_CMAKE_SET_RE = re.compile(r"^\s*set\(\s*(?P<name>[A-Z0-9_]+)\s+\"(?P<value>[^\"]+)\"\s*\)\s*$")


def _extract_cmake_var(content: str, name: str) -> str | None:
    for line in content.splitlines():
        m = _CMAKE_SET_RE.match(line)
        if not m:
            continue
        if m.group("name") == name:
            return m.group("value")
    return None
