from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

from ms.core.hashing import sha256_file
from ms.core.result import Err, Ok, Result
from ms.platform.files import atomic_write_text, remove_tree
from ms.platform.process import ProcessError, run_silent
from ms.services.base import BaseService
from ms.services.build.service import BuildService
from ms.services.ux_workflow.models import (
    UxAppNotFound,
    UxBuildFailed,
    UxExecutableMissing,
    UxOutputPathUnsafe,
    UxProcessRunner,
    UxReportFailed,
    UxRunFailed,
    UxWorkflow,
    UxWorkflowApp,
    UxWorkflowCatalog,
    UxWorkflowDirectoryMissing,
    UxWorkflowError,
    UxWorkflowRun,
)
from ms.services.ux_workflow.presentation import report_lines
from ms.services.ux_workflow.provenance import write_run_manifest
from ms.services.ux_workflow.selection import selected_workflows
from ms.services.ux_workflow.verification import inspect_run

if TYPE_CHECKING:
    from ms.core.config import Config
    from ms.core.workspace import Workspace
    from ms.output.console import ConsoleProtocol
    from ms.platform.detection import PlatformInfo


class UxWorkflowService(BaseService):
    """Discover workspace workflows and coordinate execution and artifact writes."""

    def __init__(
        self,
        *,
        workspace: Workspace,
        platform: PlatformInfo,
        config: Config | None,
        console: ConsoleProtocol,
        runner: UxProcessRunner | None = None,
    ) -> None:
        super().__init__(workspace=workspace, platform=platform, config=config, console=console)
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
                        path=path, relative_path=path.relative_to(app.workflow_dir).as_posix()
                    )
                    for path in app.workflow_dir.rglob("*.ux") if path.is_file()
                ),
                key=lambda item: item.relative_path.lower(),
            )
        )
        return Ok(UxWorkflowCatalog(app=app, workflows=workflows))

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
        selected_result = selected_workflows(
            catalog=catalog, selections=selections, all_workflows=all_workflows,
        )
        if isinstance(selected_result, Err):
            return selected_result
        selected = selected_result.value
        exe_result = self._resolve_executable(
            app=catalog.app, skip_build=skip_build, executable=executable,
        )
        if isinstance(exe_result, Err):
            return exe_result
        exe = exe_result.value
        executable_sha256 = sha256_file(exe)
        root = (output_root or catalog.app.output_root).resolve()
        root.mkdir(parents=True, exist_ok=True)
        if all_workflows and output_root is None:
            _clear_generated_workflow_outputs(root)

        runs: list[UxWorkflowRun] = []
        for workflow in selected:
            run_result = self._run_one(
                app=catalog.app, workflow=workflow, executable=exe,
                executable_sha256=executable_sha256, output_root=root,
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
        selected_result = selected_workflows(
            catalog=catalog, selections=selections, all_workflows=all_workflows,
        )
        if isinstance(selected_result, Err):
            return selected_result
        root = (output_root or catalog.app.output_root).resolve()
        if not root.is_dir():
            return Err(UxReportFailed(message=f"workflow output directory not found: {root}"))
        destination = (report_path or (root / "report.md")).resolve()
        destination.parent.mkdir(parents=True, exist_ok=True)
        lines = report_lines(
            catalog=catalog, workflows=selected_result.value,
            output_root=root, report_dir=destination.parent,
        )
        if isinstance(lines, Err):
            return Err(lines.error)
        atomic_write_text(destination, "\n".join(lines.value) + "\n", encoding="utf-8")
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
                workspace=self._workspace, platform=self._platform,
                config=self._config, console=self._console,
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
        executable_sha256: str,
        output_root: Path,
    ) -> Result[UxWorkflowRun, UxWorkflowError]:
        output_dir = (output_root / workflow.id).resolve()
        if not output_dir.is_relative_to(output_root.resolve()):
            return Err(UxOutputPathUnsafe(output_root=output_root, output_dir=output_dir))
        if output_dir.exists():
            remove_tree(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        run_utc = datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")
        process_result = self._runner(
            [str(executable), "--ux-script", str(workflow.path), "--ux-output", str(output_dir)],
            app.repo_dir, None,
        )
        process_error: ProcessError | None = None
        exit_code = 0
        if isinstance(process_result, Err):
            process_error = process_result.error
            exit_code = process_error.returncode
        run = inspect_run(workflow=workflow, output_dir=output_dir, exit_code=exit_code)
        try:
            write_run_manifest(
                app=app, workflow=workflow, executable=executable,
                executable_sha256=executable_sha256, output_dir=output_dir,
                run=run, run_utc=run_utc,
            )
        except OSError as error:
            return Err(
                UxReportFailed(
                    message=f"failed to write UX run provenance for "
                    f"'{workflow.relative_path}': {error}"
                )
            )
        if process_error is not None:
            return Err(UxRunFailed(workflow=workflow, process_error=process_error, run=run))
        return Ok(run)


def _clear_generated_workflow_outputs(root: Path) -> None:
    for child in root.iterdir():
        if child.is_dir():
            remove_tree(child)
        elif child.name == "report.md":
            child.unlink()


def _run_ux_process(
    cmd: list[str], cwd: Path, timeout: float | None,
) -> Result[None, ProcessError]:
    return run_silent(cmd, cwd=cwd, timeout=timeout)
