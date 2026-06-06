from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal, NoReturn

import typer

from ms.cli.context import CLIContext, build_context
from ms.cli.selector import SelectorOption, is_interactive_terminal, select_one, select_one_with_run
from ms.core.errors import ErrorCode
from ms.core.result import Err, Ok
from ms.output.console import ConsoleProtocol, Style
from ms.services.ux_workflows import (
    UxWorkflowCatalog,
    UxWorkflowError,
    UxWorkflowRun,
    UxWorkflowService,
    ux_error_kind,
    ux_error_message,
    workflow_tree_lines,
)

ux_app = typer.Typer(
    add_completion=False,
    no_args_is_help=False,
    rich_markup_mode="rich",
)


@dataclass(frozen=True, slots=True)
class _TreeChoice:
    kind: Literal["current", "folder", "file"]
    path: str


@ux_app.callback(invoke_without_command=True)
def ux_root(ctx: typer.Context) -> None:
    """Run app UX workflows."""
    if ctx.invoked_subcommand is not None:
        return
    _interactive_root()


@ux_app.command("list")
def list_cmd(
    app_name: str = typer.Argument("core", metavar="APP", help="App/repo name."),
) -> None:
    """List UX workflow scripts as a copyable tree."""
    ctx = build_context()
    service = _service(ctx)
    catalog = _catalog_or_exit(service=service, app_name=app_name, console=ctx.console)
    _print_tree(catalog=catalog, console=ctx.console)


@ux_app.command("run")
def run_cmd(
    app_name: str | None = typer.Argument(None, metavar="APP", help="App/repo name."),
    select: list[str] | None = typer.Option(
        None,
        "--select",
        "-s",
        help="Workflow file or folder to run. Can be passed more than once.",
    ),
    all_workflows: bool = typer.Option(
        False,
        "--all",
        help="Run all UX workflows for the app.",
    ),
    skip_build: bool = typer.Option(
        False,
        "--skip-build",
        help="Use an existing native executable.",
    ),
    executable: Path | None = typer.Option(
        None,
        "--exe",
        help="Native executable to run.",
    ),
    output_root: Path | None = typer.Option(
        None,
        "--output-root",
        help="Capture output root.",
    ),
    report: bool = typer.Option(
        False,
        "--report",
        help="Write a Markdown report after successful replay.",
    ),
    no_interactive: bool = typer.Option(
        False,
        "--no-interactive",
        help="Fail instead of opening the workflow selector.",
    ),
) -> None:
    """Run selected UX workflows."""
    ctx = build_context()
    service = _service(ctx)
    app = _resolve_app_name(service=service, app_name=app_name, console=ctx.console)
    catalog = _catalog_or_exit(service=service, app_name=app, console=ctx.console)

    selections = tuple(select or ())
    if not selections and not all_workflows:
        if no_interactive or not is_interactive_terminal():
            ctx.console.error("choose workflows with --all or --select")
            raise typer.Exit(code=int(ErrorCode.USER_ERROR))
        selection = _select_workflow_tree(service=service, catalog=catalog, verb="run")
        if selection is None:
            raise typer.Exit(code=0)
        selections = (selection,)

    result = service.run(
        app_name=app,
        selections=selections,
        all_workflows=all_workflows,
        skip_build=skip_build,
        executable=executable,
        output_root=output_root,
    )
    match result:
        case Ok(runs):
            _print_runs(runs=runs, console=ctx.console)
        case Err(error):
            _exit_ux_error(error, ctx.console)

    if report:
        report_result = service.write_report(
            app_name=app,
            selections=selections,
            all_workflows=all_workflows,
            output_root=output_root,
        )
        match report_result:
            case Ok(path):
                ctx.console.success(f"UX report written: {path}")
            case Err(error):
                _exit_ux_error(error, ctx.console)


@ux_app.command("report")
def report_cmd(
    app_name: str = typer.Argument("core", metavar="APP", help="App/repo name."),
    select: list[str] | None = typer.Option(
        None,
        "--select",
        "-s",
        help="Workflow file or folder to include. Can be passed more than once.",
    ),
    all_workflows: bool = typer.Option(
        True,
        "--all/--selected",
        help="Include all workflows unless --selected is used with --select.",
    ),
    output_root: Path | None = typer.Option(
        None,
        "--output-root",
        help="Capture output root.",
    ),
    report_path: Path | None = typer.Option(
        None,
        "--report-path",
        help="Markdown report destination.",
    ),
) -> None:
    """Regenerate the UX Markdown report from existing captures."""
    ctx = build_context()
    service = _service(ctx)
    selections = tuple(select or ())
    result = service.write_report(
        app_name=app_name,
        selections=selections,
        all_workflows=all_workflows or not selections,
        output_root=output_root,
        report_path=report_path,
    )
    match result:
        case Ok(path):
            ctx.console.success(f"UX report written: {path}")
        case Err(error):
            _exit_ux_error(error, ctx.console)


def _interactive_root() -> None:
    if not is_interactive_terminal():
        typer.echo("error: ms ux requires a TTY; use 'ms ux run --all' or '--select'", err=True)
        raise typer.Exit(code=int(ErrorCode.USER_ERROR))

    ctx = build_context()
    service = _service(ctx)
    app_name = _select_app(service=service, console=ctx.console)
    action = select_one(
        title="ms ux",
        subtitle=f"App: {app_name}",
        options=[
            SelectorOption(value="list", label="List", detail="Print the workflow tree."),
            SelectorOption(value="run", label="Run", detail="Select and replay workflows."),
            SelectorOption(value="report", label="Report", detail="Regenerate Markdown report."),
        ],
        allow_back=True,
    )
    if action.action in {"back", "cancel"} or action.value is None:
        raise typer.Exit(code=0)

    catalog = _catalog_or_exit(service=service, app_name=app_name, console=ctx.console)
    if action.value == "list":
        _print_tree(catalog=catalog, console=ctx.console)
        return

    selection = _select_workflow_tree(service=service, catalog=catalog, verb=action.value)
    if selection is None:
        raise typer.Exit(code=0)
    if action.value == "run":
        result = service.run(
            app_name=app_name,
            selections=(selection,),
            all_workflows=False,
            skip_build=False,
        )
        match result:
            case Ok(runs):
                _print_runs(runs=runs, console=ctx.console)
            case Err(error):
                _exit_ux_error(error, ctx.console)
        return

    result = service.write_report(
        app_name=app_name,
        selections=(selection,),
        all_workflows=False,
    )
    match result:
        case Ok(path):
            ctx.console.success(f"UX report written: {path}")
        case Err(error):
            _exit_ux_error(error, ctx.console)


def _service(ctx: CLIContext) -> UxWorkflowService:
    return UxWorkflowService(
        workspace=ctx.workspace,
        platform=ctx.platform,
        config=ctx.config,
        console=ctx.console,
    )


def _resolve_app_name(
    *, service: UxWorkflowService, app_name: str | None, console: ConsoleProtocol
) -> str:
    if app_name is not None:
        return app_name
    if is_interactive_terminal():
        return _select_app(service=service, console=console)
    console.error("missing app name; use 'core' or run interactively")
    raise typer.Exit(code=int(ErrorCode.USER_ERROR))


def _select_app(*, service: UxWorkflowService, console: ConsoleProtocol) -> str:
    apps = service.available_apps()
    if not apps:
        console.error("no UX-enabled apps found in this workspace")
        raise typer.Exit(code=int(ErrorCode.ENV_ERROR))
    if len(apps) == 1:
        return apps[0].name
    result = select_one(
        title="ms ux",
        subtitle="Choose app",
        options=[
            SelectorOption(value=app.name, label=app.name, detail=str(app.workflow_dir))
            for app in apps
        ],
        allow_back=False,
    )
    if result.action == "cancel" or result.value is None:
        raise typer.Exit(code=0)
    return result.value


def _catalog_or_exit(
    *, service: UxWorkflowService, app_name: str, console: ConsoleProtocol
) -> UxWorkflowCatalog:
    result = service.catalog(app_name)
    match result:
        case Ok(catalog):
            return catalog
        case Err(error):
            _exit_ux_error(error, console)


def _select_workflow_tree(
    *, service: UxWorkflowService, catalog: UxWorkflowCatalog, verb: str
) -> str | None:
    current = ""
    while True:
        count = service.count_selection(catalog, current or ".")
        groups = service.groups(catalog, current)
        files = service.workflows_in(catalog, current)
        options = [
            SelectorOption(
                value=_TreeChoice(kind="current", path=current or "."),
                label="./",
                detail=f"Selected: {current or '.'} | Workflows: {count}",
            ),
            *[
                SelectorOption(
                    value=_TreeChoice(kind="folder", path=group.path),
                    label=f"{Path(group.path).name}/",
                    detail=f"Selected: {group.path}/ | Workflows: {group.workflow_count}",
                )
                for group in groups
            ],
        ]
        options.extend(
            SelectorOption(
                value=_TreeChoice(kind="file", path=workflow.relative_path),
                label=workflow.name,
                detail=f"Selected: {workflow.relative_path} | Workflows: 1",
            )
            for workflow in files
        )

        label = catalog.app.name if not current else f"{catalog.app.name}/{current}"
        result = select_one_with_run(
            title=f"ms ux {verb}",
            subtitle=(
                f"Current: {label} | Workflows: {count}. "
                "Enter opens folders/files; Ctrl+Enter/r runs highlighted."
            ),
            options=options,
            allow_back=True,
            run_current_label=f"{verb} highlighted",
        )
        if result.action == "run":
            return result.value.path if result.value is not None else current or "."
        if result.action == "cancel":
            return None
        if result.action == "back":
            if current == "":
                return None
            current = _parent(current)
            continue
        if result.value is None:
            return None
        if result.value.kind == "current":
            return result.value.path
        if result.value.kind == "folder":
            current = result.value.path
            continue
        return result.value.path


def _parent(path: str) -> str:
    parent = Path(path).parent.as_posix()
    return "" if parent == "." else parent


def _print_tree(*, catalog: UxWorkflowCatalog, console: ConsoleProtocol) -> None:
    console.header("ux workflows")
    for line in workflow_tree_lines(catalog):
        console.print(line)


def _print_runs(*, runs: tuple[UxWorkflowRun, ...], console: ConsoleProtocol) -> None:
    failed = tuple(run for run in runs if not run.ok)
    status = "OK" if not failed else "FAIL"
    style = Style.SUCCESS if not failed else Style.ERROR
    console.header("ux")
    console.print(f"{status}  workflows {len(runs)}  failed {len(failed)}", style)
    console.print(
        f"  {'workflow':<48} {'res':<4} {'captures':>9} {'dispatch':>8} expectations",
        Style.DIM,
    )
    for run in runs:
        expectations = ",".join(run.expectations) if run.expectations else "-"
        res = "OK" if run.ok else "FAIL"
        console.print(
            f"  {run.workflow.relative_path:<48} {res:<4} "
            f"{run.capture_count:>4}/{run.expected_capture_count:<4} "
            f"{str(run.has_dispatch):>8} {expectations}"
        )


def _exit_ux_error(error: UxWorkflowError, console: ConsoleProtocol) -> NoReturn:
    message = ux_error_message(error)
    console.error(message)
    kind = ux_error_kind(error)
    code = {
        "user": ErrorCode.USER_ERROR,
        "env": ErrorCode.ENV_ERROR,
        "build": ErrorCode.BUILD_ERROR,
        "io": ErrorCode.IO_ERROR,
    }[kind]
    raise typer.Exit(code=int(code))
