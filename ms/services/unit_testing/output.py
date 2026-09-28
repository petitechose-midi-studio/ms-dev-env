from __future__ import annotations

import re
from contextlib import suppress
from dataclasses import dataclass

from ms.core.errors import ErrorCode
from ms.output.console import ConsoleProtocol, Style
from ms.services.build_errors import ToolMissing

from .models import (
    UnitTestConfigureFailed,
    UnitTestDependencyError,
    UnitTestError,
    UnitTestFailed,
    UnitTestHarnessMissing,
    UnitTestSelectionInvalid,
    UnitTestTargetNotFound,
)


def print_unit_test_error(error: UnitTestError, console: ConsoleProtocol) -> None:
    match error:
        case ToolMissing(tool_id=tool_id, hint=hint):
            console.error(f"{tool_id}: missing")
            console.print(f"hint: {hint}", Style.DIM)
        case UnitTestTargetNotFound(name=name, available=available):
            console.error(f"Unknown test target: {name}")
            console.print(f"Available: {', '.join(available)}", Style.DIM)
        case UnitTestSelectionInvalid(target=target, message=message):
            console.error(f"{target}: invalid test selection")
            console.print(message, Style.DIM)
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
        case UnitTestTargetNotFound() | UnitTestSelectionInvalid():
            return int(ErrorCode.USER_ERROR)
        case UnitTestDependencyError():
            return int(ErrorCode.NETWORK_ERROR)
        case UnitTestConfigureFailed() | UnitTestFailed():
            return int(ErrorCode.BUILD_ERROR)
    return int(ErrorCode.INTERNAL_ERROR)


@dataclass(frozen=True, slots=True)
class TestSummary:
    total_tests: int | None
    failed_tests: int | None
    runner_seconds: float | None


def parse_ctest_summary(output: str) -> TestSummary:
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
    return TestSummary(total_tests, failed_tests, ctest_seconds)


def parse_pytest_summary(output: str) -> TestSummary:
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
    return TestSummary(total_tests, failed_tests, runner_seconds)


def parse_cargo_summary(output: str) -> TestSummary:
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
    return TestSummary(
        total_tests=(passed_total + failed_total if saw_summary else None),
        failed_tests=(failed_total if saw_summary else None),
        runner_seconds=runner_seconds,
    )


def parse_npm_summary(output: str) -> TestSummary:
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
    return TestSummary(total_tests, failed_tests, runner_seconds)


def process_output(*, stdout: str, stderr: str) -> str:
    return "\n".join(part for part in (stdout.strip(), stderr.strip()) if part)


def _print_output_tail(output: str, console: ConsoleProtocol) -> None:
    if not output.strip():
        return
    lines = [line for line in output.splitlines() if line.strip()]
    tail = "\n".join(lines[-120:])
    console.print("runner output tail:", Style.DIM)
    console.print(tail, Style.DIM)
