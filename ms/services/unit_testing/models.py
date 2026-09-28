from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from ms.services.build_errors import ToolMissing


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
    env_vars: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True, slots=True)
class UnitTestRun:
    name: str
    runner: UnitTestRunner
    elapsed_seconds: float
    total_tests: int | None = None
    failed_tests: int | None = None
    runner_seconds: float | None = None
    configure_seconds: float | None = None
    build_seconds: float | None = None
    dry_run: bool = False


@dataclass(frozen=True, slots=True)
class UnitTestTargetNotFound:
    name: str
    available: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class UnitTestSelectionInvalid:
    target: str
    message: str


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
    | UnitTestSelectionInvalid
    | UnitTestHarnessMissing
    | UnitTestDependencyError
    | UnitTestConfigureFailed
    | UnitTestFailed
)
