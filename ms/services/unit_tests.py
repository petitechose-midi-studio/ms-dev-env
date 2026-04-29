from __future__ import annotations

import os
import re
import shutil
import time
import tomllib
from contextlib import suppress
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, cast

from ms.core.errors import ErrorCode
from ms.core.result import Err, Ok, Result
from ms.output.console import Style
from ms.platform.process import run
from ms.services.base import BaseService
from ms.services.build_errors import ToolMissing
from ms.services.toolchains.checksum import sha256_file
from ms.tools.download import Downloader
from ms.tools.http import RealHttpClient
from ms.tools.installer import Installer

if TYPE_CHECKING:
    from ms.output.console import ConsoleProtocol

_CONFIGURE_TIMEOUT_SECONDS = 20 * 60.0
_TEST_TIMEOUT_SECONDS = 20 * 60.0
_TEST_DEPENDENCIES_PATH = Path(__file__).resolve().parents[1] / "data" / "test_dependencies.toml"


class UnitTestRunner(Enum):
    CMAKE = "cmake"
    CARGO = "cargo"
    CARGO_CHECK = "cargo-check"
    NPM = "npm"
    PYTEST = "pytest"


@dataclass(frozen=True, slots=True)
class UnitTestTarget:
    name: str
    runner: UnitTestRunner
    source_dir: Path
    build_dir: Path
    label: str
    dependencies: tuple[str, ...] = ()
    runner_args: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class UnitTestRun:
    name: str
    runner: UnitTestRunner
    elapsed_seconds: float
    total_tests: int | None = None
    failed_tests: int | None = None
    runner_seconds: float | None = None
    dry_run: bool = False


@dataclass(frozen=True, slots=True)
class UnitTestTargetNotFound:
    name: str
    available: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class UnitTestHarnessMissing:
    target: str
    path: Path


@dataclass(frozen=True, slots=True)
class UnitTestDependencyError:
    dependency: str
    message: str
    hint: str | None = None


@dataclass(frozen=True, slots=True)
class UnitTestConfigureFailed:
    target: str
    returncode: int
    output: str = ""


@dataclass(frozen=True, slots=True)
class UnitTestFailed:
    target: str
    returncode: int
    output: str = ""


UnitTestError = (
    ToolMissing
    | UnitTestTargetNotFound
    | UnitTestHarnessMissing
    | UnitTestDependencyError
    | UnitTestConfigureFailed
    | UnitTestFailed
)


@dataclass(frozen=True, slots=True)
class _TestDependencyPin:
    name: str
    version: str
    url: str
    sha256: str
    strip_components: int


class UnitTestService(BaseService):
    """Run workspace tests through one guided CLI path."""

    def target_groups(self) -> dict[str, tuple[str, ...]]:
        return _target_groups(self._target_map())

    def available_targets(self) -> tuple[str, ...]:
        return tuple(self._target_map())

    def available_groups(self) -> tuple[str, ...]:
        return tuple(self.target_groups())

    def list_entries(self) -> tuple[tuple[str, str, str], ...]:
        entries: list[tuple[str, str, str]] = []
        for group, targets in self.target_groups().items():
            entries.append((group, "group", ", ".join(targets)))
        for target in self._target_map().values():
            entries.append((target.name, target.runner.value, str(target.source_dir)))
        return tuple(entries)

    def run(
        self,
        *,
        target: str,
        dry_run: bool = False,
        verbose: bool = False,
    ) -> Result[tuple[UnitTestRun, ...], UnitTestError]:
        targets_result = self._resolve_targets(target)
        if isinstance(targets_result, Err):
            return targets_result

        if target in self.target_groups():
            return self._run_group(
                targets=targets_result.value,
                dry_run=dry_run,
                verbose=verbose,
            )

        runs: list[UnitTestRun] = []
        for unit_target in targets_result.value:
            run_result = self._run_single_target(
                unit_target=unit_target,
                dry_run=dry_run,
                verbose=verbose,
            )
            if isinstance(run_result, Err):
                return run_result
            runs.append(run_result.value)

        return Ok(tuple(runs))

    def _run_single_target(
        self,
        *,
        unit_target: UnitTestTarget,
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

        unity = self._ensure_test_dependency(name="unity", dry_run=dry_run)
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
            dry_run=dry_run,
            verbose=verbose,
        )
        if isinstance(built, Err):
            return built

        return self._run_ctest(
            unit_target=unit_target,
            build_dir=unit_target.build_dir,
            dry_run=dry_run,
            verbose=verbose,
        )

    def _run_group(
        self,
        *,
        targets: tuple[UnitTestTarget, ...],
        dry_run: bool,
        verbose: bool,
    ) -> Result[tuple[UnitTestRun, ...], UnitTestError]:
        if all(target.runner == UnitTestRunner.CMAKE for target in targets):
            return self._run_cmake_group(
                targets=targets,
                dry_run=dry_run,
                verbose=verbose,
            )

        runs: list[UnitTestRun] = []
        cmake_batch: list[UnitTestTarget] = []

        def flush_cmake_batch() -> Result[None, UnitTestError]:
            if not cmake_batch:
                return Ok(None)
            result = self._run_cmake_group(
                targets=tuple(cmake_batch),
                dry_run=dry_run,
                verbose=verbose,
            )
            cmake_batch.clear()
            if isinstance(result, Err):
                return result
            runs.extend(result.value)
            return Ok(None)

        for target in targets:
            if target.runner == UnitTestRunner.CMAKE:
                cmake_batch.append(target)
                continue

            flushed = flush_cmake_batch()
            if isinstance(flushed, Err):
                return flushed
            run_result = self._run_single_target(
                unit_target=target,
                dry_run=dry_run,
                verbose=verbose,
            )
            if isinstance(run_result, Err):
                return run_result
            runs.append(run_result.value)

        flushed = flush_cmake_batch()
        if isinstance(flushed, Err):
            return flushed
        return Ok(tuple(runs))

    def _run_cmake_group(
        self,
        *,
        targets: tuple[UnitTestTarget, ...],
        dry_run: bool,
        verbose: bool,
    ) -> Result[tuple[UnitTestRun, ...], UnitTestError]:
        build_root = self._workspace.build_dir / "tests" / self._toolchain_build_id()
        source_dir = build_root / "workspace-source"
        build_dir = build_root / "workspace"
        source_dir.mkdir(parents=True, exist_ok=True)

        unity = self._ensure_test_dependency(name="unity", dry_run=dry_run)
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
        for unit_target in targets:
            tested = self._run_ctest(
                unit_target=unit_target,
                build_dir=build_dir,
                dry_run=dry_run,
                verbose=verbose,
                label=unit_target.label,
            )
            if isinstance(tested, Err):
                return tested
            runs.append(tested.value)

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
    ) -> Result[None, UnitTestError]:
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
            return Ok(None)

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
                    output=_process_output(
                        stdout=configure.error.stdout,
                        stderr=configure.error.stderr,
                    ),
                )
            )
        if verbose and configure.value:
            self._console.print(configure.value.rstrip(), Style.DIM)
        return Ok(None)

    def _build(
        self,
        *,
        target_name: str,
        build_dir: Path,
        dry_run: bool,
        verbose: bool,
    ) -> Result[None, UnitTestError]:
        cmake = self._get_tool_path("cmake")
        if isinstance(cmake, Err):
            return cmake

        build_args = [str(cmake.value), "--build", str(build_dir)]
        if verbose or dry_run:
            self._console.print(" ".join(build_args), Style.DIM)
        if dry_run:
            return Ok(None)

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
                    output=_process_output(stdout=build.error.stdout, stderr=build.error.stderr),
                )
            )
        if verbose and build.value:
            self._console.print(build.value.rstrip(), Style.DIM)
        return Ok(None)

    def _run_ctest(
        self,
        *,
        unit_target: UnitTestTarget,
        build_dir: Path,
        dry_run: bool,
        verbose: bool,
        label: str | None = None,
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

        if verbose or dry_run:
            self._console.print(" ".join(ctest_args), Style.DIM)
        output = ""
        if not dry_run:
            tests = run(
                ctest_args,
                cwd=self._workspace.root,
                env=self._base_env(),
                timeout=_TEST_TIMEOUT_SECONDS,
            )
            if isinstance(tests, Err):
                return Err(
                    UnitTestFailed(
                        target=unit_target.name,
                        returncode=tests.error.returncode,
                        output=_process_output(
                            stdout=tests.error.stdout,
                            stderr=tests.error.stderr,
                        ),
                    )
                )
            output = tests.value
            if verbose and output:
                self._console.print(output.rstrip(), Style.DIM)

        summary = _parse_ctest_summary(output)
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
                        output=_process_output(
                            stdout=tested.error.stdout,
                            stderr=tested.error.stderr,
                        ),
                    )
                )
            output = tested.value
            if verbose and output:
                self._console.print(output.rstrip(), Style.DIM)

        summary = (
            _parse_cargo_summary(output)
            if unit_target.runner == UnitTestRunner.CARGO
            else _CTestSummary(total_tests=None, failed_tests=None, runner_seconds=None)
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
            env = self._base_env()
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
                        output=_process_output(
                            stdout=tested.error.stdout,
                            stderr=tested.error.stderr,
                        ),
                    )
                )
            output = tested.value
            if verbose and output:
                self._console.print(output.rstrip(), Style.DIM)

        summary = _parse_pytest_summary(output)
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
                        output=_process_output(
                            stdout=tested.error.stdout,
                            stderr=tested.error.stderr,
                        ),
                    )
                )
            output = tested.value
            if verbose and output:
                self._console.print(output.rstrip(), Style.DIM)

        summary = _parse_npm_summary(output)
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

    def _resolve_targets(self, target: str) -> Result[tuple[UnitTestTarget, ...], UnitTestError]:
        targets = self._target_map()
        groups = self.target_groups()

        if target in groups:
            return Ok(_topological_targets({name: targets[name] for name in groups[target]}))

        selected = targets.get(target)
        if selected is None:
            return Err(
                UnitTestTargetNotFound(
                    name=target,
                    available=(*self.available_groups(), *self.available_targets()),
                )
            )

        return Ok((selected,))

    def _target_map(self) -> dict[str, UnitTestTarget]:
        build_root = self._workspace.build_dir / "tests" / self._toolchain_build_id()
        return {
            "ms-dev-env": UnitTestTarget(
                name="ms-dev-env",
                runner=UnitTestRunner.PYTEST,
                source_dir=self._workspace.root,
                build_dir=build_root / "ms-dev-env",
                label="ms-dev-env",
            ),
            "protocol-codegen": UnitTestTarget(
                name="protocol-codegen",
                runner=UnitTestRunner.PYTEST,
                source_dir=self._workspace.open_control_dir / "protocol-codegen",
                build_dir=build_root / "protocol-codegen",
                label="protocol-codegen",
            ),
            "open-control-bridge": UnitTestTarget(
                name="open-control-bridge",
                runner=UnitTestRunner.CARGO,
                source_dir=self._workspace.open_control_dir / "bridge",
                build_dir=build_root / "open-control-bridge",
                label="open-control-bridge",
            ),
            "midi-studio-loader": UnitTestTarget(
                name="midi-studio-loader",
                runner=UnitTestRunner.CARGO,
                source_dir=self._workspace.midi_studio_dir / "loader",
                build_dir=build_root / "midi-studio-loader",
                label="midi-studio-loader",
            ),
            "ms-manager-svelte": UnitTestTarget(
                name="ms-manager-svelte",
                runner=UnitTestRunner.NPM,
                source_dir=self._workspace.root / "ms-manager",
                build_dir=build_root / "ms-manager-svelte",
                label="ms-manager-svelte",
                runner_args=("run", "check"),
            ),
            "ms-manager-node": UnitTestTarget(
                name="ms-manager-node",
                runner=UnitTestRunner.NPM,
                source_dir=self._workspace.root / "ms-manager",
                build_dir=build_root / "ms-manager-node",
                label="ms-manager-node",
                runner_args=("run", "test:tauri-versioning"),
            ),
            "ms-manager-core": UnitTestTarget(
                name="ms-manager-core",
                runner=UnitTestRunner.CARGO,
                source_dir=self._workspace.root / "ms-manager" / "crates" / "ms-manager-core",
                build_dir=build_root / "ms-manager-core",
                label="ms-manager-core",
            ),
            "ms-manager-tauri": UnitTestTarget(
                name="ms-manager-tauri",
                runner=UnitTestRunner.CARGO_CHECK,
                source_dir=self._workspace.root / "ms-manager" / "src-tauri",
                build_dir=build_root / "ms-manager-tauri",
                label="ms-manager-tauri",
                runner_args=("check", "--locked"),
            ),
            "open-control-framework": UnitTestTarget(
                name="open-control-framework",
                runner=UnitTestRunner.CMAKE,
                source_dir=self._workspace.open_control_dir / "framework",
                build_dir=build_root / "open-control-framework",
                label="open-control-framework",
            ),
            "open-control-note": UnitTestTarget(
                name="open-control-note",
                runner=UnitTestRunner.CMAKE,
                source_dir=self._workspace.open_control_dir / "note",
                build_dir=build_root / "open-control-note",
                label="open-control-note",
                dependencies=("open-control-framework",),
            ),
            "open-control-hal-midi": UnitTestTarget(
                name="open-control-hal-midi",
                runner=UnitTestRunner.CMAKE,
                source_dir=self._workspace.open_control_dir / "hal-midi",
                build_dir=build_root / "open-control-hal-midi",
                label="open-control-hal-midi",
            ),
            "core": UnitTestTarget(
                name="core",
                runner=UnitTestRunner.CMAKE,
                source_dir=self._workspace.midi_studio_dir / "core",
                build_dir=build_root / "midi-studio-core",
                label="core",
                dependencies=("open-control-framework", "open-control-note"),
            ),
            "plugin-bitwig": UnitTestTarget(
                name="plugin-bitwig",
                runner=UnitTestRunner.CMAKE,
                source_dir=self._workspace.midi_studio_dir / "plugin-bitwig",
                build_dir=build_root / "midi-studio-plugin-bitwig",
                label="plugin-bitwig",
            ),
        }

    def _base_env(self) -> dict[str, str]:
        env = os.environ.copy()
        env.update(self._registry.get_env_vars())
        env.update(self._workspace.platformio_env_vars())
        return env

    def _get_tool_path(self, tool_id: str) -> Result[Path, UnitTestError]:
        path = self._registry.get_bin_path(tool_id)
        if path is not None and path.exists():
            return Ok(path)

        found = shutil.which(tool_id)
        if found:
            return Ok(Path(found))

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
        }
        if any(path is None or not path.exists() for path in wrappers.values()):
            return Err(ToolMissing(tool_id="zig"))

        return Ok([f"-D{name}={path}" for name, path in wrappers.items() if path is not None])

    def _toolchain_build_id(self) -> str:
        if self._platform.platform.is_windows:
            return "zig-windows-gnu"
        return "host"

    def _ensure_test_dependency(
        self,
        *,
        name: str,
        dry_run: bool,
    ) -> Result[Path, UnitTestError]:
        pin = load_test_dependency_pin(name)
        if isinstance(pin, Err):
            return pin

        install_dir = self._workspace.cache_dir / "test-deps" / pin.value.name / pin.value.version
        expected_header = install_dir / "src" / "unity.h"
        expected_source = install_dir / "src" / "unity.c"
        marker = install_dir / ".ms-test-dependency"

        if dry_run:
            return Ok(install_dir)

        if (
            expected_header.exists()
            and expected_source.exists()
            and marker.exists()
            and marker.read_text(encoding="utf-8").strip() == pin.value.sha256
        ):
            return Ok(install_dir)

        downloader = Downloader(RealHttpClient(timeout=60.0), self._workspace.download_cache_dir)
        downloaded = downloader.download(pin.value.url)
        if isinstance(downloaded, Err):
            return Err(
                UnitTestDependencyError(
                    dependency=name,
                    message=str(downloaded.error),
                    hint="Check network access or pre-populate the workspace download cache.",
                )
            )

        actual = sha256_file(downloaded.value.path)
        if actual != pin.value.sha256:
            return Err(
                UnitTestDependencyError(
                    dependency=name,
                    message=(
                        f"checksum mismatch for {downloaded.value.path}: "
                        f"expected {pin.value.sha256}, got {actual}"
                    ),
                    hint=f"Review {_TEST_DEPENDENCIES_PATH}.",
                )
            )

        installed = Installer().install(
            downloaded.value.path,
            install_dir,
            strip_components=pin.value.strip_components,
        )
        if isinstance(installed, Err):
            return Err(
                UnitTestDependencyError(
                    dependency=name,
                    message=str(installed.error),
                    hint="Remove the test dependency cache and retry.",
                )
            )

        if not expected_header.exists() or not expected_source.exists():
            return Err(
                UnitTestDependencyError(
                    dependency=name,
                    message=f"installed dependency is missing Unity sources in {install_dir}",
                    hint=f"Review {_TEST_DEPENDENCIES_PATH}.",
                )
            )

        marker.write_text(f"{pin.value.sha256}\n", encoding="utf-8")
        self._console.print(f"{name}: test dependency ready", Style.DIM)
        return Ok(install_dir)

    def _write_superbuild(self, *, source_dir: Path, targets: tuple[UnitTestTarget, ...]) -> None:
        lines = [
            "cmake_minimum_required(VERSION 3.29)",
            "",
            "project(ms_workspace_unit_tests LANGUAGES C CXX)",
            "",
            "include(CTest)",
            "",
            'set(OC_FRAMEWORK_BUILD_TESTS ON CACHE BOOL "Build OpenControl framework tests" FORCE)',
            'set(OC_HAL_MIDI_BUILD_TESTS ON CACHE BOOL "Build OpenControl HAL MIDI tests" FORCE)',
            'set(OC_NOTE_BUILD_TESTS ON CACHE BOOL "Build OpenControl note tests" FORCE)',
            'set(MS_CORE_BUILD_TESTS ON CACHE BOOL "Build MIDI Studio core tests" FORCE)',
            (
                'set(MS_PLUGIN_BITWIG_BUILD_TESTS ON CACHE BOOL '
                '"Build MIDI Studio Bitwig plugin tests" FORCE)'
            ),
            "",
        ]
        for target in targets:
            lines.append(
                f'add_subdirectory("{_cmake_path(target.source_dir)}" "{target.name}")'
            )
        lines.append("")
        (source_dir / "CMakeLists.txt").write_text("\n".join(lines), encoding="utf-8")


def print_unit_test_error(error: UnitTestError, console: ConsoleProtocol) -> None:
    match error:
        case ToolMissing(tool_id=tool_id, hint=hint):
            console.error(f"{tool_id}: missing")
            console.print(f"hint: {hint}", Style.DIM)
        case UnitTestTargetNotFound(name=name, available=available):
            console.error(f"Unknown test target: {name}")
            console.print(f"Available: {', '.join(available)}", Style.DIM)
        case UnitTestHarnessMissing(target=target, path=path):
            console.error(f"{target}: CMake unit-test harness missing")
            console.print(f"expected: {path}", Style.DIM)
        case UnitTestDependencyError(dependency=dependency, message=message, hint=hint):
            console.error(f"{dependency}: test dependency unavailable")
            console.print(message, Style.DIM)
            if hint:
                console.print(f"hint: {hint}", Style.DIM)
        case UnitTestConfigureFailed(target=target, returncode=returncode, output=output):
            console.error(f"{target}: cmake configure failed (exit {returncode})")
            _print_output_tail(output, console)
        case UnitTestFailed(target=target, returncode=returncode, output=output):
            console.error(f"{target}: unit tests failed (exit {returncode})")
            _print_output_tail(output, console)


def unit_test_error_exit_code(error: UnitTestError) -> int:
    match error:
        case ToolMissing() | UnitTestHarnessMissing():
            return int(ErrorCode.ENV_ERROR)
        case UnitTestTargetNotFound():
            return int(ErrorCode.USER_ERROR)
        case UnitTestDependencyError():
            return int(ErrorCode.NETWORK_ERROR)
        case UnitTestConfigureFailed() | UnitTestFailed():
            return int(ErrorCode.BUILD_ERROR)
    return int(ErrorCode.INTERNAL_ERROR)


def _topological_targets(targets: dict[str, UnitTestTarget]) -> tuple[UnitTestTarget, ...]:
    ordered: list[UnitTestTarget] = []
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(name: str) -> None:
        if name in visited:
            return
        if name in visiting:
            raise ValueError(f"cycle in unit test target dependencies: {name}")
        visiting.add(name)
        target = targets[name]
        for dependency in target.dependencies:
            visit(dependency)
        visiting.remove(name)
        visited.add(name)
        ordered.append(target)

    for name in targets:
        visit(name)

    return tuple(ordered)


def _target_groups(targets: dict[str, UnitTestTarget]) -> dict[str, tuple[str, ...]]:
    del targets
    firmware = (
        "open-control-framework",
        "open-control-hal-midi",
        "open-control-note",
        "core",
        "plugin-bitwig",
    )
    app = (
        "open-control-bridge",
        "midi-studio-loader",
        "ms-manager-svelte",
        "ms-manager-node",
        "ms-manager-core",
        "ms-manager-tauri",
    )
    env = ("ms-dev-env", "protocol-codegen")
    return {
        "all": (*env, *app, *firmware),
        "env": env,
        "app": app,
        "firmware": firmware,
    }


def _cmake_path(path: Path) -> str:
    return path.resolve().as_posix()


def _join_env_path(first: str, rest: str | None) -> str:
    if not rest:
        return first
    return f"{first}{os.pathsep}{rest}"


def load_test_dependency_pin(name: str) -> Result[_TestDependencyPin, UnitTestError]:
    try:
        with open(_TEST_DEPENDENCIES_PATH, "rb") as f:
            data = tomllib.load(f)
    except OSError as e:
        return Err(
            UnitTestDependencyError(
                dependency=name,
                message=f"failed to read {_TEST_DEPENDENCIES_PATH}: {e}",
            )
        )
    except tomllib.TOMLDecodeError as e:
        return Err(
            UnitTestDependencyError(
                dependency=name,
                message=f"invalid TOML in {_TEST_DEPENDENCIES_PATH}: {e}",
            )
        )

    raw = data.get(name)
    if not isinstance(raw, dict):
        return Err(
            UnitTestDependencyError(
                dependency=name,
                message=f"missing [{name}] in {_TEST_DEPENDENCIES_PATH}",
            )
        )

    entry = cast("dict[str, object]", raw)
    version = entry.get("version")
    url = entry.get("url")
    digest = entry.get("sha256")
    strip_components = entry.get("strip_components", 0)
    if (
        not isinstance(version, str)
        or not isinstance(url, str)
        or not isinstance(digest, str)
        or not isinstance(strip_components, int)
        or len(digest) != 64
    ):
        return Err(
            UnitTestDependencyError(
                dependency=name,
                message=f"invalid [{name}] entry in {_TEST_DEPENDENCIES_PATH}",
            )
        )

    return Ok(
        _TestDependencyPin(
            name=name,
            version=version,
            url=url,
            sha256=digest.lower(),
            strip_components=strip_components,
        )
    )


@dataclass(frozen=True, slots=True)
class _CTestSummary:
    total_tests: int | None
    failed_tests: int | None
    runner_seconds: float | None


def _parse_ctest_summary(output: str) -> _CTestSummary:
    total_tests: int | None = None
    failed_tests: int | None = None
    ctest_seconds: float | None = None

    for line in output.splitlines():
        stripped = line.strip()
        if "tests passed," in stripped and "tests failed out of" in stripped:
            parts = stripped.split()
            with suppress(ValueError, IndexError):
                failed_tests = int(parts[3])
                total_tests = int(parts[-1])
        elif stripped.startswith("Total Test time (real) ="):
            with suppress(ValueError, IndexError):
                ctest_seconds = float(stripped.rsplit("=", maxsplit=1)[1].split()[0])

    return _CTestSummary(
        total_tests=total_tests,
        failed_tests=failed_tests,
        runner_seconds=ctest_seconds,
    )


def _parse_pytest_summary(output: str) -> _CTestSummary:
    total_tests: int | None = None
    failed_tests: int | None = None
    runner_seconds: float | None = None

    summary_re = re.compile(
        r"=*\s*(?:(?P<failed>\d+) failed,\s+)?(?P<passed>\d+) passed.*"
        r"in (?P<seconds>[0-9.]+)s\s*=*"
    )
    for line in output.splitlines():
        match = summary_re.search(line.strip())
        if match is None:
            continue
        passed = int(match.group("passed"))
        failed = int(match.group("failed") or 0)
        total_tests = passed + failed
        failed_tests = failed
        runner_seconds = float(match.group("seconds"))

    return _CTestSummary(
        total_tests=total_tests,
        failed_tests=failed_tests,
        runner_seconds=runner_seconds,
    )


def _parse_cargo_summary(output: str) -> _CTestSummary:
    passed_total = 0
    failed_total = 0
    saw_summary = False
    runner_seconds: float | None = None

    summary_re = re.compile(
        r"test result: (?P<status>ok|FAILED)\. "
        r"(?P<passed>\d+) passed; (?P<failed>\d+) failed; .* finished in "
        r"(?P<seconds>[0-9.]+)s"
    )
    for line in output.splitlines():
        match = summary_re.search(line.strip())
        if match is None:
            continue
        saw_summary = True
        passed_total += int(match.group("passed"))
        failed_total += int(match.group("failed"))
        seconds = float(match.group("seconds"))
        runner_seconds = seconds if runner_seconds is None else runner_seconds + seconds

    return _CTestSummary(
        total_tests=(passed_total + failed_total if saw_summary else None),
        failed_tests=(failed_total if saw_summary else None),
        runner_seconds=runner_seconds,
    )


def _parse_npm_summary(output: str) -> _CTestSummary:
    total_tests: int | None = None
    failed_tests: int | None = None
    runner_seconds: float | None = None

    for line in output.splitlines():
        stripped = line.strip()
        parts = stripped.split()
        with suppress(ValueError, IndexError):
            if len(parts) >= 3 and parts[1] == "tests":
                total_tests = int(parts[2])
            elif len(parts) >= 3 and parts[1] == "fail":
                failed_tests = int(parts[2])
            elif len(parts) >= 3 and parts[1] == "duration_ms":
                runner_seconds = float(parts[2]) / 1000.0

    return _CTestSummary(
        total_tests=total_tests,
        failed_tests=failed_tests,
        runner_seconds=runner_seconds,
    )


def _process_output(*, stdout: str, stderr: str) -> str:
    return "\n".join(part for part in (stdout.strip(), stderr.strip()) if part)


def _print_output_tail(output: str, console: ConsoleProtocol) -> None:
    if not output.strip():
        return
    lines = [line for line in output.splitlines() if line.strip()]
    tail = "\n".join(lines[-120:])
    console.print("runner output tail:", Style.DIM)
    console.print(tail, Style.DIM)
