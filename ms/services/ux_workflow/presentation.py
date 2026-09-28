from __future__ import annotations

from pathlib import Path
from typing import Literal

from .models import (
    UxAppNotFound,
    UxBuildFailed,
    UxExecutableMissing,
    UxOutputPathUnsafe,
    UxReportFailed,
    UxRunFailed,
    UxWorkflow,
    UxWorkflowCatalog,
    UxWorkflowDirectoryMissing,
    UxWorkflowError,
    UxWorkflowNotFound,
    UxWorkflowRun,
    UxWorkflowSelectionAmbiguous,
)
from .provenance import read_run_manifest, run_manifest_provenance
from .selection import folder_prefix
from .verification import inspect_run, workflow_expectations


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
                    f"semantic={run.semantic_capture_count}/"
                    f"{run.expected_semantic_capture_count} "
                    f"semantic_schema={run.semantic_schema_valid} "
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
    lines: list[str], *, workflows: tuple[UxWorkflow, ...], parent: str, indent: str,
) -> None:
    prefix = folder_prefix(parent)
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
            tags = _expectation_suffix(workflow_expectations(workflow.path))
            lines.append(f"{indent}{branch}{Path(path).name}{tags}")


def _expectation_suffix(expectations: tuple[str, ...]) -> str:
    if not expectations:
        return ""
    labels: list[str] = []
    capture_matches = 0
    capture_changes = 0
    semantic_facts = 0
    for expectation in expectations:
        if expectation.startswith("capture_match:"):
            capture_matches += 1
            continue
        if expectation.startswith("capture_changed:"):
            capture_changes += 1
            continue
        if expectation.startswith("semantic:"):
            semantic_facts += 1
            continue
        labels.append(expectation)
    if capture_matches == 1:
        labels.append("capture_match:*")
    elif capture_matches > 1:
        labels.append(f"capture_match:*x{capture_matches}")
    if capture_changes == 1:
        labels.append("capture_changed:*")
    elif capture_changes > 1:
        labels.append(f"capture_changed:*x{capture_changes}")
    if semantic_facts == 1:
        labels.append("semantic:*")
    elif semantic_facts > 1:
        labels.append(f"semantic:*x{semantic_facts}")
    return f" expects={','.join(labels)}"


def report_lines(
    *, catalog: UxWorkflowCatalog, workflows: tuple[UxWorkflow, ...],
    output_root: Path, report_dir: Path,
) -> tuple[str, ...]:
    lines = [
        "# UX Workflow Report", "",
        f"App: {catalog.app.name}",
        f"Source scripts: {_relative(catalog.app.workflow_dir, catalog.app.repo_dir)}",
        f"Output root: {_relative(output_root, catalog.app.repo_dir)}",
        "", "## Summary", "",
        "| Workflow | Provenance | Captures | Semantic | Schema | Run End | Dispatch | "
        "Expectations |",
        "|---|---|---:|---:|---:|---:|---:|---|",
    ]
    sections: list[str] = []
    for workflow in workflows:
        run = inspect_run(workflow=workflow, output_dir=output_root / workflow.id, exit_code=0)
        manifest = read_run_manifest(run.output_dir)
        provenance = run_manifest_provenance(
            workflow=workflow, output_dir=run.output_dir, manifest=manifest,
        )
        expectations = ", ".join(run.expectations) if run.expectations else "-"
        lines.append(
            f"| {workflow.relative_path} | {provenance} | "
            f"{run.capture_count}/{run.expected_capture_count} | "
            f"{run.semantic_capture_count}/{run.expected_semantic_capture_count} | "
            f"{run.semantic_schema_valid} | "
            f"{run.run_ended} | {run.has_dispatch} | {expectations} |"
        )
        sections.extend(
            _workflow_report_section(
                workflow=workflow, run=run, manifest=manifest, report_dir=report_dir,
            )
        )
    lines.extend(["", "## Workflows", "", *sections])
    return tuple(lines)


def _workflow_report_section(
    *, workflow: UxWorkflow, run: UxWorkflowRun,
    manifest: dict[str, object] | None, report_dir: Path,
) -> tuple[str, ...]:
    lines = [
        f"### {workflow.relative_path}", "",
        f"- Output: {_relative(run.output_dir, report_dir)}",
        f"- Captures: {run.capture_count}/{run.expected_capture_count}",
        f"- Semantic captures: {run.semantic_capture_count}/{run.expected_semantic_capture_count}",
        f"- Semantic schema: {run.semantic_schema_valid}",
        f"- Run end: {run.run_ended}",
        f"- Dispatch: {run.has_dispatch}",
    ]
    if manifest is None:
        lines.append("- Provenance: unavailable (capture predates run manifests)")
    else:
        lines.extend([
            f"- Run UTC: {manifest['run_utc']}",
            f"- Executable: {Path(str(manifest['executable'])).name}",
            f"- Binary SHA-256: `{manifest['executable_sha256']}`",
            f"- Workflow SHA-256: `{manifest['workflow_sha256']}`",
            f"- Manifest result: {str(manifest['verified']).lower()}",
        ])
    lines.append("")
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
