from __future__ import annotations

import typer

from ms.cli.context import build_context
from ms.core.result import Err, Ok
from ms.services.unit_tests import (
    UnitTestService,
    print_unit_test_error,
    unit_test_error_exit_code,
)


def test(
    target: str = typer.Argument(
        "all",
        help="Unit test target: all, core, open-control-framework, or open-control-note.",
    ),
    dry_run: bool = typer.Option(False, "--dry-run", help="Print actions without running them."),
    verbose: bool = typer.Option(
        False,
        "--verbose",
        "-v",
        help="Print CMake, Ninja, and CTest logs.",
    ),
) -> None:
    """Run unit tests through the CMake/CTest workflow."""
    ctx = build_context()
    service = UnitTestService(
        workspace=ctx.workspace,
        platform=ctx.platform,
        config=ctx.config,
        console=ctx.console,
    )

    result = service.run(target=target, dry_run=dry_run, verbose=verbose)
    match result:
        case Ok(runs):
            ctx.console.header("Unit Tests")
            for run in runs:
                status = "DRY" if run.dry_run else "OK"
                tests = (
                    f"{run.total_tests - (run.failed_tests or 0)}/{run.total_tests}"
                    if run.total_tests is not None
                    else "-"
                )
                ctest = f"ctest {run.ctest_seconds:.2f}s" if run.ctest_seconds is not None else ""
                ctx.console.print(
                    f"{run.name:<24} {status:<3} {tests:>7}  {run.elapsed_seconds:>6.2f}s  {ctest}",
                )
        case Err(error):
            print_unit_test_error(error, ctx.console)
            raise typer.Exit(code=unit_test_error_exit_code(error))
