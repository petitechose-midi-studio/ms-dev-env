from __future__ import annotations

from ms.core.config import Config
from ms.core.result import Err, Ok, Result
from ms.core.workspace import Workspace
from ms.output.console import ConsoleProtocol
from ms.platform.detection import PlatformInfo
from ms.services.base import BaseService
from ms.services.unit_testing.catalog import (
    normalize_cmake_test_targets,
    target_groups,
    target_map,
    topological_targets,
)
from ms.services.unit_testing.execution import TestExecutor
from ms.services.unit_testing.models import (
    UnitTestError,
    UnitTestRun,
    UnitTestRunner,
    UnitTestSelectionInvalid,
    UnitTestTarget,
    UnitTestTargetNotFound,
)


class UnitTestService(BaseService):
    """Select and order workspace tests, then delegate their execution."""

    def __init__(
        self,
        *,
        workspace: Workspace,
        platform: PlatformInfo,
        config: Config | None,
        console: ConsoleProtocol,
    ) -> None:
        super().__init__(workspace=workspace, platform=platform, config=config, console=console)
        self._executor = TestExecutor(
            workspace=workspace, platform=platform, console=console, registry=self._registry,
        )

    def target_groups(self) -> dict[str, tuple[str, ...]]:
        return target_groups()

    def available_targets(self) -> tuple[str, ...]:
        return tuple(target_map(self._workspace, self._platform.platform))

    def available_groups(self) -> tuple[str, ...]:
        return tuple(self.target_groups())

    def list_entries(self) -> tuple[tuple[str, str, str], ...]:
        entries: list[tuple[str, str, str]] = []
        for group, targets in self.target_groups().items():
            entries.append((group, "group", ", ".join(targets)))
        for target in target_map(self._workspace, self._platform.platform).values():
            entries.append((target.name, target.runner.value, str(target.source_dir)))
        return tuple(entries)

    def run(
        self,
        *,
        target: str,
        tests: tuple[str, ...] = (),
        dry_run: bool = False,
        verbose: bool = False,
    ) -> Result[tuple[UnitTestRun, ...], UnitTestError]:
        targets_result = self._resolve_targets(target)
        if isinstance(targets_result, Err):
            return targets_result

        selected_tests: tuple[str, ...] = ()
        if tests:
            if target in self.target_groups():
                return Err(
                    UnitTestSelectionInvalid(
                        target=target,
                        message="--test requires one CMake target, not a group",
                    )
                )
            unit_target = targets_result.value[0]
            if unit_target.runner != UnitTestRunner.CMAKE:
                return Err(
                    UnitTestSelectionInvalid(
                        target=target,
                        message="--test is available only for CMake test targets",
                    )
                )
            normalized = normalize_cmake_test_targets(tests)
            if normalized is None:
                return Err(
                    UnitTestSelectionInvalid(
                        target=target,
                        message=(
                            "test names may contain only letters, digits, '.', '_', '+', and '-'"
                        ),
                    )
                )
            selected_tests = normalized

        if target in self.target_groups():
            return self._run_group(
                targets=targets_result.value, dry_run=dry_run, verbose=verbose,
            )

        run_result = self._executor.run_target(
            unit_target=targets_result.value[0], selected_tests=selected_tests,
            dry_run=dry_run, verbose=verbose,
        )
        if isinstance(run_result, Err):
            return run_result
        return Ok((run_result.value,))

    def _run_group(
        self,
        *,
        targets: tuple[UnitTestTarget, ...],
        dry_run: bool,
        verbose: bool,
    ) -> Result[tuple[UnitTestRun, ...], UnitTestError]:
        if all(target.runner == UnitTestRunner.CMAKE for target in targets):
            return self._executor.run_cmake_group(
                targets=targets, dry_run=dry_run, verbose=verbose,
            )

        runs: list[UnitTestRun] = []
        cmake_batch: list[UnitTestTarget] = []

        def flush_cmake_batch() -> Result[None, UnitTestError]:
            if not cmake_batch:
                return Ok(None)
            result = self._executor.run_cmake_group(
                targets=tuple(cmake_batch), dry_run=dry_run, verbose=verbose,
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
            run_result = self._executor.run_target(
                unit_target=target, dry_run=dry_run, verbose=verbose,
            )
            if isinstance(run_result, Err):
                return run_result
            runs.append(run_result.value)

        flushed = flush_cmake_batch()
        if isinstance(flushed, Err):
            return flushed
        return Ok(tuple(runs))

    def _resolve_targets(self, target: str) -> Result[tuple[UnitTestTarget, ...], UnitTestError]:
        targets = target_map(self._workspace, self._platform.platform)
        groups = self.target_groups()
        if target in groups:
            return Ok(topological_targets({name: targets[name] for name in groups[target]}))
        selected = targets.get(target)
        if selected is None:
            return Err(
                UnitTestTargetNotFound(
                    name=target, available=(*self.available_groups(), *self.available_targets()),
                )
            )
        return Ok((selected,))
