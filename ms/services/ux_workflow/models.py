from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from ms.core.result import Result
from ms.platform.process import ProcessError

type UxProcessRunner = Callable[[list[str], Path, float | None], Result[None, ProcessError]]


@dataclass(frozen=True, slots=True)
class UxWorkflowApp:
    name: str
    repo_dir: Path
    workflow_dir: Path
    output_root: Path
    executable: Path


@dataclass(frozen=True, slots=True)
class UxWorkflow:
    path: Path
    relative_path: str

    @property
    def id(self) -> str:
        return self.relative_path.removesuffix(".ux")

    @property
    def name(self) -> str:
        return Path(self.relative_path).name


@dataclass(frozen=True, slots=True)
class UxWorkflowGroup:
    path: str
    workflow_count: int

    @property
    def label(self) -> str:
        return "." if self.path == "" else self.path


@dataclass(frozen=True, slots=True)
class UxWorkflowCatalog:
    app: UxWorkflowApp
    workflows: tuple[UxWorkflow, ...]

    @property
    def total(self) -> int:
        return len(self.workflows)


@dataclass(frozen=True, slots=True)
class UxWorkflowRun:
    workflow: UxWorkflow
    output_dir: Path
    exit_code: int
    capture_count: int
    expected_capture_count: int
    run_ended: bool
    has_dispatch: bool
    semantic_capture_count: int
    expected_semantic_capture_count: int
    semantic_schema_valid: bool
    expectations: tuple[str, ...]
    failed_expectations: tuple[str, ...]

    @property
    def ok(self) -> bool:
        return (
            self.exit_code == 0
            and self.run_ended
            and self.has_dispatch
            and self.capture_count >= self.expected_capture_count
            and self.semantic_schema_valid
            and self.semantic_capture_count >= self.expected_semantic_capture_count
            and len(self.failed_expectations) == 0
        )


@dataclass(frozen=True, slots=True)
class UxAppNotFound:
    name: str
    available: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class UxWorkflowDirectoryMissing:
    app_name: str
    path: Path


@dataclass(frozen=True, slots=True)
class UxWorkflowNotFound:
    app_name: str
    selection: str


@dataclass(frozen=True, slots=True)
class UxWorkflowSelectionAmbiguous:
    app_name: str
    selection: str
    matches: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class UxExecutableMissing:
    path: Path


@dataclass(frozen=True, slots=True)
class UxBuildFailed:
    app_name: str
    message: str


@dataclass(frozen=True, slots=True)
class UxRunFailed:
    workflow: UxWorkflow
    process_error: ProcessError | None
    run: UxWorkflowRun | None


@dataclass(frozen=True, slots=True)
class UxOutputPathUnsafe:
    output_root: Path
    output_dir: Path


@dataclass(frozen=True, slots=True)
class UxReportFailed:
    message: str


type UxWorkflowError = (
    UxAppNotFound
    | UxWorkflowDirectoryMissing
    | UxWorkflowNotFound
    | UxWorkflowSelectionAmbiguous
    | UxExecutableMissing
    | UxBuildFailed
    | UxRunFailed
    | UxOutputPathUnsafe
    | UxReportFailed
)
