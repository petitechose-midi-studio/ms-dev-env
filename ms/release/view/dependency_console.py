from __future__ import annotations

from ms.output.console import ConsoleProtocol, Style
from ms.release.domain.dependency_readiness_models import DependencyReadinessReport


def print_dependency_readiness_report(
    *, console: ConsoleProtocol, report: DependencyReadinessReport
) -> None:
    console.header("Dependency readiness")
    for item in report.items:
        if item.status == "ok":
            sha = item.sha[:12] if item.sha is not None else "unknown"
            console.success(f"{item.repo}: ready ({sha})")
            continue

        console.warning(f"{item.repo}: {item.status}")
        if item.detail:
            console.print(item.detail, Style.DIM)
        if item.hint:
            console.print(f"hint: {item.hint}", Style.DIM)
