from __future__ import annotations

import os
import re
import shutil
import time
from pathlib import Path

from ms.core.result import Err, Ok, Result
from ms.core.workspace import Workspace
from ms.output.console import ConsoleProtocol, Style
from ms.platform.detection import PlatformInfo
from ms.platform.files import atomic_write_text
from ms.platform.process import run
from ms.services.build_errors import ToolMissing
from ms.services.toolchain_env import base_env
from ms.tools.registry import ToolRegistry

from .catalog import toolchain_build_id
from .dependencies import ensure_test_dependency
from .models import (
    UnitTestConfigureFailed,
    UnitTestDependencyError,
    UnitTestError,
    UnitTestFailed,
    UnitTestHarnessMissing,
    UnitTestRun,
    UnitTestRunner,
    UnitTestTarget,
)
from .output import (
    TestSummary,
    parse_cargo_summary,
    parse_ctest_summary,
    parse_npm_summary,
    parse_pytest_summary,
    process_output,
)

_CONFIGURE_TIMEOUT_SECONDS = 20 * 60.0
_TEST_TIMEOUT_SECONDS = 20 * 60.0


class TestExecutor:
    """Execute resolved test targets; selection and catalog policy live in the service."""

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

    def run_target(
        self,
        *,
        unit_target: UnitTestTarget,
        selected_tests: tuple[str, ...] = (),
        dry_run: bool,
        verbose: bool,
    ) -> Result[UnitTestRun, UnitTestError]:
        if unit_target.runner in (UnitTestRunner.CARGO, UnitTestRunner.CARGO_CHECK):
            return self._run_cargo_target(
                unit_target=unit_target,
                dry_run=dry_run,
                verbose=verbose,
            )
        if unit_target.runner == UnitTestRunner.NPM:
            return self._run_npm_target(
                unit_target=unit_target,
                dry_run=dry_run,
                verbose=verbose,
            )
        if unit_target.runner == UnitTestRunner.PYTEST:
            return self._run_pytest_target(
                unit_target=unit_target,
                dry_run=dry_run,
                verbose=verbose,
            )

        harness = unit_target.source_dir / "CMakeLists.txt"
        if not harness.exists():
            return Err(UnitTestHarnessMissing(target=unit_target.name, path=harness))

        unity = ensure_test_dependency(
            workspace=self._workspace, console=self._console, name="unity", dry_run=dry_run,
        )
        if isinstance(unity, Err):
            return unity

        configured = self._configure(
            target_name=unit_target.name,
            source_dir=unit_target.source_dir,
            build_dir=unit_target.build_dir,
            dry_run=dry_run,
            verbose=verbose,
            extra_args=(
                [f"-DMS_UNITY_SOURCE_DIR={_cmake_path(unity.value)}"]
                + (
                    [f"-DMS_CORE_OPEN_CONTROL_ROOT={_cmake_path(self._workspace.open_control_dir)}"]
                    if unit_target.name == "core"
                    else []
                )
            ),
        )
        if isinstance(configured, Err):
            return configured

        built = self._build(
            target_name=unit_target.name,
            build_dir=unit_target.build_dir,
            build_targets=selected_tests,
            dry_run=dry_run,
            verbose=verbose,
        )
        if isinstance(built, Err):
            return built

        tested = self._run_ctest(
            unit_target=unit_target,
            build_dir=unit_target.build_dir,
            test_names=selected_tests,
            dry_run=dry_run,
            verbose=verbose,
        )
        if isinstance(tested, Err):
            return tested
        return Ok(
            _with_cmake_timings(
                tested.value,
                configure_seconds=configured.value,
                build_seconds=built.value,
            )
        )

    def run_cmake_group(
        self,
        *,
        targets: tuple[UnitTestTarget, ...],
        dry_run: bool,
        verbose: bool,
    ) -> Result[tuple[UnitTestRun, ...], UnitTestError]:
        build_root = (
            self._workspace.build_dir / "tests" / toolchain_build_id(self._platform.platform)
        )
        source_dir = build_root / "workspace-source"
        build_dir = build_root / "workspace"
        source_dir.mkdir(parents=True, exist_ok=True)

        unity = ensure_test_dependency(
            workspace=self._workspace, console=self._console, name="unity", dry_run=dry_run,
        )
        if isinstance(unity, Err):
            return unity

        self._write_superbuild(source_dir=source_dir, targets=targets)

        configured = self._configure(
            target_name="all",
            source_dir=source_dir,
            build_dir=build_dir,
            dry_run=dry_run,
            verbose=verbose,
            extra_args=[f"-DMS_UNITY_SOURCE_DIR={_cmake_path(unity.value)}"],
        )
        if isinstance(configured, Err):
            return configured

        built = self._build(
            target_name="all",
            build_dir=build_dir,
            dry_run=dry_run,
            verbose=verbose,
        )
        if isinstance(built, Err):
            return built

        runs: list[UnitTestRun] = []
        for index, unit_target in enumerate(targets):
            tested = self._run_ctest(
                unit_target=unit_target,
                build_dir=build_dir,
                dry_run=dry_run,
                verbose=verbose,
                label=unit_target.label,
            )
            if isinstance(tested, Err):
                return tested
            runs.append(
                _with_cmake_timings(
                    tested.value,
                    configure_seconds=configured.value if index == 0 else 0.0,
                    build_seconds=built.value if index == 0 else 0.0,
                )
            )

        return Ok(tuple(runs))

    def _configure(
        self,
        *,
        target_name: str,
        source_dir: Path,
        build_dir: Path,
        dry_run: bool,
        verbose: bool,
        extra_args: list[str],
    ) -> Result[float, UnitTestError]:
        started_at = time.perf_counter()
        cmake = self._get_tool_path("cmake")
        if isinstance(cmake, Err):
            return cmake
        ninja = self._get_tool_path("ninja")
        if isinstance(ninja, Err):
            return ninja

        build_dir.mkdir(parents=True, exist_ok=True)
        configure_args = [
            str(cmake.value),
            "-G",
            "Ninja",
            "-S",
            str(source_dir),
            "-B",
            str(build_dir),
            "-DCMAKE_BUILD_TYPE=Debug",
            "-DBUILD_TESTING=ON",
            f"-DCMAKE_MAKE_PROGRAM={ninja.value}",
        ]
        compiler_args = self._compiler_args()
        if isinstance(compiler_args, Err):
            return compiler_args
        configure_args.extend(compiler_args.value)
        configure_args.extend(extra_args)

        if verbose or dry_run:
            self._console.print(" ".join(configure_args), Style.DIM)
        if dry_run:
            return Ok(0.0)

        configure = run(
            configure_args,
            cwd=self._workspace.root,
            env=self._base_env(),
            timeout=_CONFIGURE_TIMEOUT_SECONDS,
        )
        if isinstance(configure, Err):
            return Err(
                UnitTestConfigureFailed(
                    target=target_name,
                    returncode=configure.error.returncode,
                    output=process_output(
                        stdout=configure.error.stdout,
                        stderr=configure.error.stderr,
                    ),
                )
            )
        if verbose and configure.value:
            self._console.print(configure.value.rstrip(), Style.DIM)
        return Ok(time.perf_counter() - started_at)

    def _build(
        self,
        *,
        target_name: str,
        build_dir: Path,
        build_targets: tuple[str, ...] = (),
        dry_run: bool,
        verbose: bool,
    ) -> Result[float, UnitTestError]:
        started_at = time.perf_counter()
        cmake = self._get_tool_path("cmake")
        if isinstance(cmake, Err):
            return cmake

        build_args = [str(cmake.value), "--build", str(build_dir)]
        if build_targets:
            build_args.extend(["--target", *build_targets])
        if verbose or dry_run:
            self._console.print(" ".join(build_args), Style.DIM)
        if dry_run:
            return Ok(0.0)

        build = run(
            build_args,
            cwd=self._workspace.root,
            env=self._base_env(),
            timeout=_TEST_TIMEOUT_SECONDS,
        )
        if isinstance(build, Err):
            return Err(
                UnitTestFailed(
                    target=target_name,
                    returncode=build.error.returncode,
                    output=process_output(stdout=build.error.stdout, stderr=build.error.stderr),
                )
            )
        if verbose and build.value:
            self._console.print(build.value.rstrip(), Style.DIM)
        return Ok(time.perf_counter() - started_at)

    def _run_ctest(
        self,
        *,
        unit_target: UnitTestTarget,
        build_dir: Path,
        dry_run: bool,
        verbose: bool,
        label: str | None = None,
        test_names: tuple[str, ...] = (),
    ) -> Result[UnitTestRun, UnitTestError]:
        started_at = time.perf_counter()
        ctest = self._ctest_path()
        if isinstance(ctest, Err):
            return ctest

        ctest_args = [
            str(ctest.value),
            "--test-dir",
            str(build_dir),
            "--parallel",
            "--output-on-failure",
        ]
        if label is not None:
            ctest_args.extend(["-L", label])
        if test_names:
            names_pattern = "|".join(re.escape(name) for name in test_names)
            ctest_args.extend(["-R", f"^({names_pattern})$", "--no-tests=error"])

        if verbose or dry_run:
            self._console.print(" ".join(ctest_args), Style.DIM)
        output = ""
        if not dry_run:
            tests = run(
                ctest_args,
                cwd=self._workspace.root,
                env=self._ctest_env(unit_target),
                timeout=_TEST_TIMEOUT_SECONDS,
            )
            if isinstance(tests, Err):
                return Err(
                    UnitTestFailed(
                        target=unit_target.name,
                        returncode=tests.error.returncode,
                        output=process_output(
                            stdout=tests.error.stdout,
                            stderr=tests.error.stderr,
                        ),
                    )
                )
            output = tests.value
            if verbose and output:
                self._console.print(output.rstrip(), Style.DIM)

        summary = parse_ctest_summary(output)
        return Ok(
            UnitTestRun(
                name=unit_target.name,
                runner=unit_target.runner,
                elapsed_seconds=time.perf_counter() - started_at,
                total_tests=summary.total_tests,
                failed_tests=summary.failed_tests,
                runner_seconds=summary.runner_seconds,
                dry_run=dry_run,
            )
        )

    def _run_cargo_target(
        self,
        *,
        unit_target: UnitTestTarget,
        dry_run: bool,
        verbose: bool,
    ) -> Result[UnitTestRun, UnitTestError]:
        started_at = time.perf_counter()
        cargo = shutil.which("cargo")
        if cargo is None:
            return Err(ToolMissing(tool_id="cargo", hint="Install Rust via https://rustup.rs/"))

        args = [cargo, *(unit_target.runner_args or ("test", "--locked"))]
        if verbose or dry_run:
            self._console.print(" ".join(args), Style.DIM)
        output = ""
        if not dry_run:
            tested = run(
                args,
                cwd=unit_target.source_dir,
                env=self._base_env(),
                timeout=_TEST_TIMEOUT_SECONDS,
            )
            if isinstance(tested, Err):
                return Err(
                    UnitTestFailed(
                        target=unit_target.name,
                        returncode=tested.error.returncode,
                        output=process_output(
                            stdout=tested.error.stdout,
                            stderr=tested.error.stderr,
                        ),
                    )
                )
            output = tested.value
            if verbose and output:
                self._console.print(output.rstrip(), Style.DIM)

        summary = (
            parse_cargo_summary(output)
            if unit_target.runner == UnitTestRunner.CARGO
            else TestSummary(total_tests=None, failed_tests=None, runner_seconds=None)
        )
        return Ok(
            UnitTestRun(
                name=unit_target.name,
                runner=unit_target.runner,
                elapsed_seconds=time.perf_counter() - started_at,
                total_tests=summary.total_tests,
                failed_tests=summary.failed_tests,
                runner_seconds=summary.runner_seconds,
                dry_run=dry_run,
            )
        )

    def _run_pytest_target(
        self,
        *,
        unit_target: UnitTestTarget,
        dry_run: bool,
        verbose: bool,
    ) -> Result[UnitTestRun, UnitTestError]:
        started_at = time.perf_counter()
        uv = shutil.which("uv")
        if uv is None:
            return Err(ToolMissing(tool_id="uv", hint="Install uv: https://docs.astral.sh/uv/"))

        if unit_target.source_dir == self._workspace.root:
            args = [uv, "run", "pytest", "-q"]
        else:
            args = [uv, "run", "--project", str(unit_target.source_dir), "pytest", "-q"]
        if verbose:
            args.remove("-q")

        if verbose or dry_run:
            self._console.print(" ".join(args), Style.DIM)
        output = ""
        if not dry_run:
            env = self._target_env(unit_target)
            src_dir = unit_target.source_dir / "src"
            if src_dir.exists():
                env["PYTHONPATH"] = _join_env_path(str(src_dir), env.get("PYTHONPATH"))
            tested = run(
                args,
                cwd=unit_target.source_dir,
                env=env,
                timeout=_TEST_TIMEOUT_SECONDS,
            )
            if isinstance(tested, Err):
                return Err(
                    UnitTestFailed(
                        target=unit_target.name,
                        returncode=tested.error.returncode,
                        output=process_output(
                            stdout=tested.error.stdout,
                            stderr=tested.error.stderr,
                        ),
                    )
                )
            output = tested.value
            if verbose and output:
                self._console.print(output.rstrip(), Style.DIM)

        summary = parse_pytest_summary(output)
        return Ok(
            UnitTestRun(
                name=unit_target.name,
                runner=unit_target.runner,
                elapsed_seconds=time.perf_counter() - started_at,
                total_tests=summary.total_tests,
                failed_tests=summary.failed_tests,
                runner_seconds=summary.runner_seconds,
                dry_run=dry_run,
            )
        )

    def _run_npm_target(
        self,
        *,
        unit_target: UnitTestTarget,
        dry_run: bool,
        verbose: bool,
    ) -> Result[UnitTestRun, UnitTestError]:
        started_at = time.perf_counter()
        npm = shutil.which("npm")
        if npm is None:
            return Err(ToolMissing(tool_id="npm", hint="Install Node.js and npm."))
        if not unit_target.runner_args:
            return Err(
                UnitTestDependencyError(
                    dependency=unit_target.name,
                    message="npm test target is missing runner arguments",
                )
            )

        args = [npm, *unit_target.runner_args]
        if verbose or dry_run:
            self._console.print(" ".join(args), Style.DIM)
        output = ""
        if not dry_run:
            tested = run(
                args,
                cwd=unit_target.source_dir,
                env=self._base_env(),
                timeout=_TEST_TIMEOUT_SECONDS,
            )
            if isinstance(tested, Err):
                return Err(
                    UnitTestFailed(
                        target=unit_target.name,
                        returncode=tested.error.returncode,
                        output=process_output(
                            stdout=tested.error.stdout,
                            stderr=tested.error.stderr,
                        ),
                    )
                )
            output = tested.value
            if verbose and output:
                self._console.print(output.rstrip(), Style.DIM)

        summary = parse_npm_summary(output)
        return Ok(
            UnitTestRun(
                name=unit_target.name,
                runner=unit_target.runner,
                elapsed_seconds=time.perf_counter() - started_at,
                total_tests=summary.total_tests,
                failed_tests=summary.failed_tests,
                runner_seconds=summary.runner_seconds,
                dry_run=dry_run,
            )
        )

    def _base_env(self) -> dict[str, str]:
        return base_env(registry=self._registry, workspace=self._workspace)

    def _target_env(self, target: UnitTestTarget) -> dict[str, str]:
        env = self._base_env()
        env.update(dict(target.env_vars))
        return env

    def _ctest_env(self, target: UnitTestTarget) -> dict[str, str]:
        """Runtime env for native test executables.

        Configure/build need the full toolchain environment. The compiled
        CTest executables do not, and leaking unrelated tool env can perturb
        native Windows test processes.
        """
        env = os.environ.copy()
        venv_dir = self._workspace.root / ".venv"
        venv_scripts = venv_dir / ("Scripts" if self._platform.platform.is_windows else "bin")
        env["PATH"] = remove_env_path_entry(env.get("PATH", ""), venv_scripts)
        if Path(env.get("VIRTUAL_ENV", "")).resolve() == venv_dir.resolve():
            env.pop("VIRTUAL_ENV", None)
        env.update(dict(target.env_vars))
        return env

    def _get_tool_path(self, tool_id: str) -> Result[Path, UnitTestError]:
        path = self._registry.resolve_executable(tool_id)
        if path is not None:
            return Ok(path)
        return Err(ToolMissing(tool_id=tool_id))

    def _ctest_path(self) -> Result[Path, UnitTestError]:
        cmake = self._get_tool_path("cmake")
        if isinstance(cmake, Err):
            return cmake
        ctest = cmake.value.with_name(self._platform.platform.exe_name("ctest"))
        if ctest.exists():
            return Ok(ctest)
        return Err(ToolMissing(tool_id="ctest", hint="Run: uv run ms sync --tools"))

    def _compiler_args(self) -> Result[list[str], UnitTestError]:
        if not self._platform.platform.is_windows:
            return Ok([])

        wrappers = {
            "CMAKE_C_COMPILER": self._registry.get_zig_wrapper("zig-cc"),
            "CMAKE_CXX_COMPILER": self._registry.get_zig_wrapper("zig-cxx"),
            "CMAKE_AR": self._registry.get_zig_wrapper("zig-ar"),
            "CMAKE_RANLIB": self._registry.get_zig_wrapper("zig-ranlib"),
            "CMAKE_RC_COMPILER": self._registry.get_zig_wrapper("zig-rc"),
        }
        if any(path is None or not path.exists() for path in wrappers.values()):
            return Err(ToolMissing(tool_id="zig"))

        return Ok([
            f"-D{name}:FILEPATH={path.as_posix()}"
            for name, path in wrappers.items()
            if path is not None
        ])

    def _write_superbuild(self, *, source_dir: Path, targets: tuple[UnitTestTarget, ...]) -> None:
        lines = [
            "cmake_minimum_required(VERSION 3.29)",
            "",
            "project(ms_workspace_unit_tests LANGUAGES C CXX)",
            "",
            "set(CMAKE_CXX_SCAN_FOR_MODULES OFF)",
            "",
            "include(CTest)",
            "",
            'set(OC_FRAMEWORK_BUILD_TESTS ON CACHE BOOL "Build OpenControl framework tests" FORCE)',
            'set(OC_HAL_MIDI_BUILD_TESTS ON CACHE BOOL "Build OpenControl HAL MIDI tests" FORCE)',
            'set(OC_NOTE_BUILD_TESTS ON CACHE BOOL "Build OpenControl note tests" FORCE)',
            'set(MS_CORE_BUILD_TESTS ON CACHE BOOL "Build MIDI Studio core tests" FORCE)',
            (
                "set(MS_PLUGIN_BITWIG_BUILD_TESTS ON CACHE BOOL "
                '"Build MIDI Studio Bitwig plugin tests" FORCE)'
            ),
            "",
        ]
        for target in targets:
            lines.append(f'add_subdirectory("{_cmake_path(target.source_dir)}" "{target.name}")')
        lines.append("")
        atomic_write_text(source_dir / "CMakeLists.txt", "\n".join(lines), encoding="utf-8")


def _with_cmake_timings(
    run: UnitTestRun,
    *,
    configure_seconds: float,
    build_seconds: float,
) -> UnitTestRun:
    return UnitTestRun(
        name=run.name,
        runner=run.runner,
        elapsed_seconds=run.elapsed_seconds + configure_seconds + build_seconds,
        total_tests=run.total_tests,
        failed_tests=run.failed_tests,
        runner_seconds=run.runner_seconds,
        configure_seconds=configure_seconds,
        build_seconds=build_seconds,
        dry_run=run.dry_run,
    )


def _cmake_path(path: Path) -> str:
    return path.resolve().as_posix()


def _join_env_path(first: str, rest: str | None) -> str:
    if not rest:
        return first
    return f"{first}{os.pathsep}{rest}"


def remove_env_path_entry(value: str, blocked: Path) -> str:
    if not value:
        return value
    blocked_norm = str(blocked.resolve()).casefold()
    kept = [
        entry
        for entry in value.split(os.pathsep)
        if str(Path(entry).resolve()).casefold() != blocked_norm
    ]
    return os.pathsep.join(kept)
