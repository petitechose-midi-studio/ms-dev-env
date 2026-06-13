from __future__ import annotations

import hashlib
import json
import re
import shutil
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Literal, cast

from ms.core.result import Err, Ok, Result
from ms.platform.process import ProcessError, run_silent
from ms.services.base import BaseService
from ms.services.build.service import BuildService

type UxProcessRunner = Callable[[list[str], Path, float | None], Result[None, ProcessError]]

_EXPECT_RE = re.compile(r"^\s*#\s*Expect:\s*(.+)$", re.IGNORECASE)
_CAPTURE_RE = re.compile(r"^\s*\d+\s+capture\s+(screen|controller)\s+([A-Za-z0-9_-]+)\s*$")
_OVERLAY_EXCLUSIVE_MAX_CHANGED_BYTE_RATIO = 0.02

if TYPE_CHECKING:
    from ms.core.config import Config
    from ms.core.workspace import Workspace
    from ms.output.console import ConsoleProtocol
    from ms.platform.detection import PlatformInfo


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
    expectations: tuple[str, ...]
    failed_expectations: tuple[str, ...]

    @property
    def ok(self) -> bool:
        return (
            self.exit_code == 0
            and self.run_ended
            and self.has_dispatch
            and self.capture_count >= self.expected_capture_count
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


class UxWorkflowService(BaseService):
    def __init__(
        self,
        *,
        workspace: Workspace,
        platform: PlatformInfo,
        config: Config | None,
        console: ConsoleProtocol,
        runner: UxProcessRunner | None = None,
    ) -> None:
        super().__init__(
            workspace=workspace,
            platform=platform,
            config=config,
            console=console,
        )
        self._runner = runner or _run_ux_process

    def available_apps(self) -> tuple[UxWorkflowApp, ...]:
        core_repo = self._workspace.midi_studio_dir / "core"
        core = UxWorkflowApp(
            name="core",
            repo_dir=core_repo,
            workflow_dir=core_repo / "sdl" / "integration" / "workflows",
            output_root=core_repo / ".captures" / "ux" / "workflows",
            executable=self._workspace.bin_dir
            / "core"
            / "native"
            / self._platform.platform.exe_name("midi_studio_core"),
        )
        return (core,) if core.workflow_dir.is_dir() else ()

    def app(self, name: str) -> Result[UxWorkflowApp, UxAppNotFound]:
        apps = self.available_apps()
        for app in apps:
            if app.name == name:
                return Ok(app)
        return Err(UxAppNotFound(name=name, available=tuple(app.name for app in apps)))

    def catalog(self, app_name: str) -> Result[UxWorkflowCatalog, UxWorkflowError]:
        app_result = self.app(app_name)
        if isinstance(app_result, Err):
            return Err(app_result.error)
        app = app_result.value
        if not app.workflow_dir.is_dir():
            return Err(UxWorkflowDirectoryMissing(app_name=app.name, path=app.workflow_dir))
        workflows = tuple(
            sorted(
                (
                    UxWorkflow(
                        path=path,
                        relative_path=path.relative_to(app.workflow_dir).as_posix(),
                    )
                    for path in app.workflow_dir.rglob("*.ux")
                    if path.is_file()
                ),
                key=lambda item: item.relative_path.lower(),
            )
        )
        return Ok(UxWorkflowCatalog(app=app, workflows=workflows))

    def groups(self, catalog: UxWorkflowCatalog, parent: str = "") -> tuple[UxWorkflowGroup, ...]:
        prefix = _folder_prefix(parent)
        children: dict[str, int] = {}
        for workflow in catalog.workflows:
            if not workflow.relative_path.startswith(prefix):
                continue
            remainder = workflow.relative_path.removeprefix(prefix)
            child = remainder.split("/", 1)[0]
            if child.endswith(".ux"):
                continue
            path = f"{prefix}{child}".strip("/")
            children[path] = children.get(path, 0) + 1
        return tuple(
            UxWorkflowGroup(path=path, workflow_count=count)
            for path, count in sorted(children.items())
        )

    def workflows_in(
        self, catalog: UxWorkflowCatalog, parent: str = ""
    ) -> tuple[UxWorkflow, ...]:
        prefix = _folder_prefix(parent)
        return tuple(
            workflow
            for workflow in catalog.workflows
            if workflow.relative_path.startswith(prefix)
            and "/" not in workflow.relative_path.removeprefix(prefix)
        )

    def count_selection(self, catalog: UxWorkflowCatalog, selection: str) -> int:
        resolved = self.resolve_selection(catalog, selection)
        if isinstance(resolved, Err):
            return 0
        return len(resolved.value)

    def resolve_selection(
        self,
        catalog: UxWorkflowCatalog,
        selection: str,
    ) -> Result[tuple[UxWorkflow, ...], UxWorkflowError]:
        normalized = _normalize_selection(selection)
        if normalized in {"", "."}:
            return Ok(catalog.workflows)

        direct = [
            workflow
            for workflow in catalog.workflows
            if workflow.relative_path == normalized or workflow.id == normalized
        ]
        if len(direct) == 1:
            return Ok((direct[0],))
        if len(direct) > 1:
            return Err(
                UxWorkflowSelectionAmbiguous(
                    app_name=catalog.app.name,
                    selection=selection,
                    matches=tuple(workflow.relative_path for workflow in direct),
                )
            )

        prefix = _folder_prefix(normalized)
        nested = tuple(
            workflow for workflow in catalog.workflows if workflow.relative_path.startswith(prefix)
        )
        if nested:
            return Ok(nested)

        basename = [
            workflow
            for workflow in catalog.workflows
            if Path(workflow.relative_path).name == normalized
            or Path(workflow.id).name == normalized
        ]
        if len(basename) == 1:
            return Ok((basename[0],))
        if len(basename) > 1:
            return Err(
                UxWorkflowSelectionAmbiguous(
                    app_name=catalog.app.name,
                    selection=selection,
                    matches=tuple(workflow.relative_path for workflow in basename),
                )
            )

        return Err(UxWorkflowNotFound(app_name=catalog.app.name, selection=selection))

    def run(
        self,
        *,
        app_name: str,
        selections: tuple[str, ...],
        all_workflows: bool,
        skip_build: bool,
        executable: Path | None = None,
        output_root: Path | None = None,
    ) -> Result[tuple[UxWorkflowRun, ...], UxWorkflowError]:
        catalog_result = self.catalog(app_name)
        if isinstance(catalog_result, Err):
            return catalog_result
        catalog = catalog_result.value

        selected_result = _selected_workflows(
            service=self,
            catalog=catalog,
            selections=selections,
            all_workflows=all_workflows,
        )
        if isinstance(selected_result, Err):
            return selected_result
        selected = selected_result.value

        exe_result = self._resolve_executable(
            app=catalog.app,
            skip_build=skip_build,
            executable=executable,
        )
        if isinstance(exe_result, Err):
            return exe_result
        exe = exe_result.value

        root = (output_root or catalog.app.output_root).resolve()
        root.mkdir(parents=True, exist_ok=True)
        if all_workflows and output_root is None:
            _clear_generated_workflow_outputs(root)

        runs: list[UxWorkflowRun] = []
        for workflow in selected:
            run_result = self._run_one(
                app=catalog.app,
                workflow=workflow,
                executable=exe,
                output_root=root,
            )
            if isinstance(run_result, Err):
                return run_result
            runs.append(run_result.value)
            if not run_result.value.ok:
                return Err(UxRunFailed(workflow=workflow, process_error=None, run=run_result.value))

        return Ok(tuple(runs))

    def write_report(
        self,
        *,
        app_name: str,
        selections: tuple[str, ...],
        all_workflows: bool,
        output_root: Path | None = None,
        report_path: Path | None = None,
    ) -> Result[Path, UxWorkflowError]:
        catalog_result = self.catalog(app_name)
        if isinstance(catalog_result, Err):
            return catalog_result
        catalog = catalog_result.value
        selected_result = _selected_workflows(
            service=self,
            catalog=catalog,
            selections=selections,
            all_workflows=all_workflows,
        )
        if isinstance(selected_result, Err):
            return selected_result

        root = (output_root or catalog.app.output_root).resolve()
        if not root.is_dir():
            return Err(UxReportFailed(message=f"workflow output directory not found: {root}"))
        destination = (report_path or (root / "report.md")).resolve()
        destination.parent.mkdir(parents=True, exist_ok=True)

        lines = _report_lines(
            catalog=catalog,
            workflows=selected_result.value,
            output_root=root,
            report_dir=destination.parent,
        )
        destination.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return Ok(destination)

    def _resolve_executable(
        self,
        *,
        app: UxWorkflowApp,
        skip_build: bool,
        executable: Path | None,
    ) -> Result[Path, UxWorkflowError]:
        if executable is not None:
            exe = executable.expanduser().resolve()
            return Ok(exe) if exe.is_file() else Err(UxExecutableMissing(path=exe))

        if not skip_build:
            builder = BuildService(
                workspace=self._workspace,
                platform=self._platform,
                config=self._config,
                console=self._console,
            )
            build_result = builder.build_native(app_name=app.name)
            if isinstance(build_result, Err):
                return Err(UxBuildFailed(app_name=app.name, message=str(build_result.error)))
            return Ok(build_result.value)

        exe = app.executable.resolve()
        return Ok(exe) if exe.is_file() else Err(UxExecutableMissing(path=exe))

    def _run_one(
        self,
        *,
        app: UxWorkflowApp,
        workflow: UxWorkflow,
        executable: Path,
        output_root: Path,
    ) -> Result[UxWorkflowRun, UxWorkflowError]:
        output_dir = (output_root / workflow.id).resolve()
        if not _is_relative_to(output_dir, output_root.resolve()):
            return Err(UxOutputPathUnsafe(output_root=output_root, output_dir=output_dir))
        if output_dir.exists():
            shutil.rmtree(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        process_result = self._runner(
            [str(executable), "--ux-script", str(workflow.path), "--ux-output", str(output_dir)],
            app.repo_dir,
            None,
        )
        process_error: ProcessError | None = None
        exit_code = 0
        if isinstance(process_result, Err):
            process_error = process_result.error
            exit_code = process_error.returncode

        run = _inspect_run(workflow=workflow, output_dir=output_dir, exit_code=exit_code)
        if process_error is not None:
            return Err(UxRunFailed(workflow=workflow, process_error=process_error, run=run))
        return Ok(run)


def print_ux_error(error: UxWorkflowError, console_message: Callable[[str], None]) -> None:
    console_message(ux_error_message(error))


def ux_error_message(error: UxWorkflowError) -> str:
    match error:
        case UxAppNotFound(name=name, available=available):
            detail = ", ".join(available) if available else "none"
            return f"unknown UX app '{name}' (available: {detail})"
        case UxWorkflowDirectoryMissing(app_name=app_name, path=path):
            return f"UX workflow directory for '{app_name}' was not found: {path}"
        case UxWorkflowNotFound(app_name=app_name, selection=selection):
            return f"UX selection '{selection}' was not found for '{app_name}'"
        case UxWorkflowSelectionAmbiguous(selection=selection, matches=matches):
            return f"UX selection '{selection}' is ambiguous: {', '.join(matches)}"
        case UxExecutableMissing(path=path):
            return f"native executable not found: {path}"
        case UxBuildFailed(app_name=app_name, message=message):
            return f"failed to build UX app '{app_name}': {message}"
        case UxRunFailed(workflow=workflow, process_error=process_error, run=run):
            if process_error is not None:
                return (
                    f"UX workflow '{workflow.relative_path}' failed "
                    f"(exit {process_error.returncode}): {process_error.stderr}"
                )
            if run is not None:
                return (
                    f"UX workflow '{workflow.relative_path}' did not verify: "
                    f"captures={run.capture_count}/{run.expected_capture_count} "
                    f"run_end={run.run_ended} dispatch={run.has_dispatch} "
                    f"expectation_failures={','.join(run.failed_expectations)}"
                )
            return f"UX workflow '{workflow.relative_path}' failed"
        case UxOutputPathUnsafe(output_root=output_root, output_dir=output_dir):
            return f"refusing to write outside output root '{output_root}': {output_dir}"
        case UxReportFailed(message=message):
            return message


def ux_error_kind(error: UxWorkflowError) -> Literal["user", "env", "build", "io"]:
    match error:
        case UxAppNotFound() | UxWorkflowNotFound() | UxWorkflowSelectionAmbiguous():
            return "user"
        case UxWorkflowDirectoryMissing() | UxExecutableMissing():
            return "env"
        case UxBuildFailed() | UxRunFailed():
            return "build"
        case UxOutputPathUnsafe() | UxReportFailed():
            return "io"


def workflow_tree_lines(catalog: UxWorkflowCatalog) -> tuple[str, ...]:
    lines = [f"{catalog.app.name} ({catalog.total} workflows)"]
    _append_tree_lines(lines, workflows=catalog.workflows, parent="", indent="")
    return tuple(lines)


def _append_tree_lines(
    lines: list[str], *, workflows: tuple[UxWorkflow, ...], parent: str, indent: str
) -> None:
    prefix = _folder_prefix(parent)
    folder_counts: dict[str, int] = {}
    files: list[UxWorkflow] = []
    for workflow in workflows:
        if not workflow.relative_path.startswith(prefix):
            continue
        remainder = workflow.relative_path.removeprefix(prefix)
        first, sep, _rest = remainder.partition("/")
        if sep:
            folder = f"{prefix}{first}".strip("/")
            folder_counts[folder] = folder_counts.get(folder, 0) + 1
        else:
            files.append(workflow)

    folders = sorted(folder_counts)
    entries: list[tuple[str, str]] = [(folder, "folder") for folder in folders]
    entries.extend((workflow.relative_path, "file") for workflow in files)

    for index, (path, kind) in enumerate(entries):
        branch = "`-- " if index == len(entries) - 1 else "|-- "
        if kind == "folder":
            count = folder_counts[path]
            lines.append(f"{indent}{branch}{Path(path).name}/ ({count})")
            next_indent = indent + ("    " if index == len(entries) - 1 else "|   ")
            _append_tree_lines(lines, workflows=workflows, parent=path, indent=next_indent)
        else:
            workflow = next(item for item in workflows if item.relative_path == path)
            tags = _expectation_suffix(_workflow_expectations(workflow.path))
            lines.append(f"{indent}{branch}{Path(path).name}{tags}")


def _expectation_suffix(expectations: tuple[str, ...]) -> str:
    if not expectations:
        return ""
    labels: list[str] = []
    capture_matches = 0
    for expectation in expectations:
        if expectation.startswith("capture_match:"):
            capture_matches += 1
            continue
        labels.append(expectation)
    if capture_matches == 1:
        labels.append("capture_match:*")
    elif capture_matches > 1:
        labels.append(f"capture_match:*x{capture_matches}")
    return f" expects={','.join(labels)}"


def _selected_workflows(
    *,
    service: UxWorkflowService,
    catalog: UxWorkflowCatalog,
    selections: tuple[str, ...],
    all_workflows: bool,
) -> Result[tuple[UxWorkflow, ...], UxWorkflowError]:
    if all_workflows:
        return Ok(catalog.workflows)
    if not selections:
        return Ok(())

    by_path: dict[str, UxWorkflow] = {}
    for selection in selections:
        resolved = service.resolve_selection(catalog, selection)
        if isinstance(resolved, Err):
            return resolved
        for workflow in resolved.value:
            by_path[workflow.relative_path] = workflow
    return Ok(tuple(by_path[path] for path in sorted(by_path)))


def _inspect_run(*, workflow: UxWorkflow, output_dir: Path, exit_code: int) -> UxWorkflowRun:
    trace_path = output_dir / "trace.ndjson"
    binding_trace_path = output_dir / "binding-trace.ndjson"
    trace_rows = _read_ndjson(trace_path)
    binding_rows = _read_ndjson(binding_trace_path)
    expectations = _workflow_expectations(workflow.path)
    failed = _failed_expectations(
        expectations=expectations,
        trace_rows=trace_rows,
        output_dir=output_dir,
    )

    return UxWorkflowRun(
        workflow=workflow,
        output_dir=output_dir,
        exit_code=exit_code,
        capture_count=len(tuple(output_dir.glob("*.bmp"))),
        expected_capture_count=_expected_capture_count(workflow.path),
        run_ended=any(row.get("event") == "run_end" for row in trace_rows),
        has_dispatch=any(row.get("stage") == "dispatch" for row in binding_rows),
        expectations=expectations,
        failed_expectations=failed,
    )


def _failed_expectations(
    *,
    expectations: tuple[str, ...],
    trace_rows: tuple[dict[str, object], ...],
    output_dir: Path,
) -> tuple[str, ...]:
    failed: list[str] = []
    for expectation in expectations:
        if expectation == "playhead_progress":
            if not _has_playhead_progress(trace_rows):
                failed.append(expectation)
            continue
        if expectation == "overlay_exclusive":
            if not _capture_mostly_match(
                output_dir,
                "selector_open_early",
                "selector_open_late",
                max_changed_byte_ratio=_OVERLAY_EXCLUSIVE_MAX_CHANGED_BYTE_RATIO,
            ):
                failed.append(expectation)
            continue
        if expectation.startswith("capture_match:"):
            labels = expectation.removeprefix("capture_match:").split("=", 1)
            if len(labels) != 2 or not labels[0] or not labels[1]:
                failed.append(expectation)
                continue
            if not _capture_match(output_dir, labels[0], labels[1]):
                failed.append(expectation)
    return tuple(failed)


def _workflow_expectations(path: Path) -> tuple[str, ...]:
    expectations: set[str] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        match = _EXPECT_RE.match(line)
        if match is None:
            continue
        expectations.update(
            item.strip().lower() for item in match.group(1).split(",") if item.strip()
        )
    return tuple(sorted(expectations))


def _expected_capture_count(path: Path) -> int:
    total = 0
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.split("#", 1)[0].split("//", 1)[0]
        if _CAPTURE_RE.match(line):
            total += 1
    return total


def _read_ndjson(path: Path) -> tuple[dict[str, object], ...]:
    if not path.is_file():
        return ()
    rows: list[dict[str, object]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        value = json.loads(line)
        if isinstance(value, dict):
            rows.append(cast(dict[str, object], value))
    return tuple(rows)


def _has_playhead_progress(rows: tuple[dict[str, object], ...]) -> bool:
    steps = {
        int(step)
        for row in rows
        if row.get("event") == "action"
        and row.get("playing") is True
        and (step := row.get("playhead_step")) is not None
        and isinstance(step, int | float)
        and step >= 0
    }
    return len(steps) > 1


def _capture_match(output_dir: Path, left_label: str, right_label: str) -> bool:
    left = _capture_for_label(output_dir, left_label)
    right = _capture_for_label(output_dir, right_label)
    if left is None or right is None:
        return False
    return _sha256(left) == _sha256(right)


def _clear_generated_workflow_outputs(root: Path) -> None:
    for child in root.iterdir():
        if child.is_dir():
            shutil.rmtree(child)
        elif child.name == "report.md":
            child.unlink()


def _capture_mostly_match(
    output_dir: Path,
    left_label: str,
    right_label: str,
    *,
    max_changed_byte_ratio: float,
) -> bool:
    left = _capture_for_label(output_dir, left_label)
    right = _capture_for_label(output_dir, right_label)
    if left is None or right is None:
        return False

    left_data = left.read_bytes()
    right_data = right.read_bytes()
    total = max(len(left_data), len(right_data))
    if total == 0:
        return len(left_data) == len(right_data)

    changed = abs(len(left_data) - len(right_data))
    changed += sum(a != b for a, b in zip(left_data, right_data, strict=False))
    return changed / total <= max_changed_byte_ratio


def _capture_for_label(output_dir: Path, label: str) -> Path | None:
    matches = tuple(output_dir.glob(f"*_{label}_screen.bmp"))
    return matches[0] if len(matches) == 1 else None


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _report_lines(
    *,
    catalog: UxWorkflowCatalog,
    workflows: tuple[UxWorkflow, ...],
    output_root: Path,
    report_dir: Path,
) -> tuple[str, ...]:
    lines = [
        "# UX Workflow Report",
        "",
        f"App: {catalog.app.name}",
        f"Source scripts: {_relative(catalog.app.workflow_dir, catalog.app.repo_dir)}",
        f"Output root: {_relative(output_root, catalog.app.repo_dir)}",
        "",
        "## Summary",
        "",
        "| Workflow | Captures | Run End | Dispatch | Expectations |",
        "|---|---:|---:|---:|---|",
    ]

    sections: list[str] = []
    for workflow in workflows:
        run = _inspect_run(workflow=workflow, output_dir=output_root / workflow.id, exit_code=0)
        expectations = ", ".join(run.expectations) if run.expectations else "-"
        lines.append(
            f"| {workflow.relative_path} | {run.capture_count}/{run.expected_capture_count} | "
            f"{run.run_ended} | {run.has_dispatch} | {expectations} |"
        )
        sections.extend(_workflow_report_section(workflow=workflow, run=run, report_dir=report_dir))

    lines.extend(["", "## Workflows", "", *sections])
    return tuple(lines)


def _workflow_report_section(
    *, workflow: UxWorkflow, run: UxWorkflowRun, report_dir: Path
) -> tuple[str, ...]:
    lines = [
        f"### {workflow.relative_path}",
        "",
        f"- Output: {_relative(run.output_dir, report_dir)}",
        f"- Captures: {run.capture_count}/{run.expected_capture_count}",
        f"- Run end: {run.run_ended}",
        f"- Dispatch: {run.has_dispatch}",
        "",
    ]
    captures = sorted(run.output_dir.glob("*.bmp"))
    if captures:
        lines.extend(["#### Captures", ""])
    for capture in captures:
        rel = _relative(capture, report_dir)
        lines.extend([f"![{capture.name}]({rel})", ""])
    return tuple(lines)


def _relative(path: Path, base: Path) -> str:
    try:
        return path.resolve().relative_to(base.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def _normalize_selection(selection: str) -> str:
    return selection.strip().replace("\\", "/").removeprefix("./").strip("/")


def _folder_prefix(path: str) -> str:
    normalized = _normalize_selection(path)
    return "" if normalized in {"", "."} else f"{normalized}/"


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _run_ux_process(
    cmd: list[str],
    cwd: Path,
    timeout: float | None,
) -> Result[None, ProcessError]:
    return run_silent(cmd, cwd=cwd, timeout=timeout)
