from __future__ import annotations

from pathlib import Path

import typer

from ms.cli.context import build_context
from ms.core.result import Err, Ok
from ms.output.console import ConsoleProtocol, Style
from ms.services.unit_tests import (
    UnitTestRun,
    UnitTestService,
    print_unit_test_error,
    unit_test_error_exit_code,
)


def test(
    target: str | None = typer.Argument(
        None,
        help=(
            "Test target or group. Run without a target to list available entries."
        ),
    ),
    dry_run: bool = typer.Option(False, "--dry-run", help="Print actions without running them."),
    verbose: bool = typer.Option(
        False,
        "--verbose",
        "-v",
        help="Print underlying test runner logs.",
    ),
) -> None:
    """Run workspace tests through the unified workflow."""
    ctx = build_context()
    service = UnitTestService(
        workspace=ctx.workspace,
        platform=ctx.platform,
        config=ctx.config,
        console=ctx.console,
    )

    if target is None:
        _print_catalog(
            service=service,
            root=ctx.workspace.root,
            console=ctx.console,
        )
        return

    result = service.run(target=target, dry_run=dry_run, verbose=verbose)
    match result:
        case Ok(runs):
            _print_runs(
                runs=runs,
                groups=service.target_groups(),
                console=ctx.console,
            )
        case Err(error):
            print_unit_test_error(error, ctx.console)
            raise typer.Exit(code=unit_test_error_exit_code(error))


def _print_catalog(
    *,
    service: UnitTestService,
    root: Path,
    console: ConsoleProtocol,
) -> None:
    entries = service.list_entries()
    groups = {
        name: tuple(item.strip() for item in detail.split(",") if item.strip())
        for name, kind, detail in entries
        if kind == "group"
    }
    targets = {
        name: (kind, _display_source(_relative_detail(detail, root)))
        for name, kind, detail in entries
        if kind != "group"
    }

    console.header("tests")
    console.print("scopes", Style.BOLD)
    console.print(f"  {'scope':<8} includes", Style.DIM)
    for name in ("all", "env", "app", "firmware"):
        if name not in groups:
            continue
        console.print(f"  {name:<8} {_group_detail(name)}", Style.DEFAULT)

    console.print("checks", Style.BOLD)
    console.print(f"  {'scope':<8} {'check':<22} {'runner':<11} source", Style.DIM)
    for scope, target in _scoped_target_names(groups):
        kind, source = targets[target]
        console.print(f"  {scope:<8} {target:<22} {kind:<11} {source}")


def _print_runs(
    *,
    runs: tuple[UnitTestRun, ...],
    groups: dict[str, tuple[str, ...]],
    console: ConsoleProtocol,
) -> None:
    elapsed = sum(run.elapsed_seconds for run in runs)
    counted_runs = [run for run in runs if run.total_tests is not None]
    total_tests = sum(run.total_tests or 0 for run in counted_runs)
    failed_tests = sum(run.failed_tests or 0 for run in runs)
    status = "DRY" if any(run.dry_run for run in runs) else "OK"
    style = Style.WARNING if status == "DRY" else Style.SUCCESS
    tests_summary = f"{total_tests - failed_tests}/{total_tests}" if counted_runs else "-"

    console.header("tests")
    console.print(
        f"{status}  checks {len(runs)}  tests {tests_summary}  time {elapsed:.2f}s",
        style,
    )
    console.print(
        f"  {'scope':<8} {'check':<22} {'runner':<11} {'res':<3} "
        f"{'tests':>7} {'time':>7} {'run':>7}",
        Style.DIM,
    )

    by_name = {run.name: run for run in runs}
    rendered: set[str] = set()
    for scope, target_name in _scoped_target_names(groups):
        run = by_name.get(target_name)
        if run is None:
            continue
        _print_run(scope, run, console)
        rendered.add(run.name)

    leftovers = [run for run in runs if run.name not in rendered]
    for run in leftovers:
        _print_run("-", run, console)


def _print_run(scope: str, run: UnitTestRun, console: ConsoleProtocol) -> None:
    status = "DRY" if run.dry_run else "OK"
    tests = (
        f"{run.total_tests - (run.failed_tests or 0)}/{run.total_tests}"
        if run.total_tests is not None
        else "-"
    )
    runner_time = f"{run.runner_seconds:.2f}s" if run.runner_seconds is not None else "-"
    console.print(
        f"  {scope:<8} {run.name:<22} {run.runner.value:<11} {status:<3} "
        f"{tests:>7} {run.elapsed_seconds:>6.2f}s {runner_time:>7}",
    )


def _group_detail(name: str) -> str:
    details = {
        "all": "env, app, firmware",
        "env": "workspace tooling, protocol codegen",
        "app": "bridge, loader, manager",
        "firmware": "C/C++ firmware and libraries",
    }
    return details[name]


def _scoped_target_names(groups: dict[str, tuple[str, ...]]) -> tuple[tuple[str, str], ...]:
    rows: list[tuple[str, str]] = []
    for scope in ("env", "app", "firmware"):
        rows.extend((scope, target) for target in groups.get(scope, ()))
    return tuple(rows)


def _relative_detail(detail: str, root: Path) -> str:
    path = Path(detail)
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return detail


def _display_source(source: str) -> str:
    replacements = {
        "open-control/": "oc/",
        "midi-studio/": "midi/",
        "ms-manager/crates/ms-manager-core": "manager/core",
        "ms-manager/src-tauri": "manager/tauri",
        "ms-manager": "manager",
    }
    for prefix, replacement in replacements.items():
        if source == prefix.rstrip("/"):
            return replacement.rstrip("/")
        if source.startswith(prefix):
            return f"{replacement}{source.removeprefix(prefix)}"
    return source
