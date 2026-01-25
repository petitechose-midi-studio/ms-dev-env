from __future__ import annotations

import typer

from ms.cli.context import CLIContext, build_context
from ms.core.errors import ErrorCode
from ms.output.console import Style
from ms.services.check import CheckService
from ms.services.checkers import CheckResult, CheckStatus


def check() -> None:
    """Check environment and suggest fixes."""
    ctx = build_context()

    service = CheckService(workspace=ctx.workspace, platform=ctx.platform, config=ctx.config)
    report = service.run()

    ctx.console.print(f"workspace: {ctx.workspace.root}", Style.DIM)
    ctx.console.print(f"platform: {ctx.platform}", Style.DIM)

    _print_group(ctx, "Workspace", report.workspace)
    _print_group(ctx, "Tools", report.tools)
    _print_group(ctx, "System", report.system)
    _print_group(ctx, "Runtime", report.runtime)

    if report.has_errors():
        raise typer.Exit(code=int(ErrorCode.ENV_ERROR))


def _print_group(ctx: CLIContext, title: str, results: list[CheckResult]) -> None:
    console = ctx.console
    console.header(title)
    for r in results:
        style = _style_for_status(r.status)
        console.print(f"{r.name}: {r.message}", style)
        if r.hint and r.status != CheckStatus.OK:
            console.print(f"hint: {r.hint}", Style.DIM)


def _style_for_status(status: CheckStatus) -> Style:
    if status == CheckStatus.OK:
        return Style.SUCCESS
    if status == CheckStatus.WARNING:
        return Style.WARNING
    return Style.ERROR
