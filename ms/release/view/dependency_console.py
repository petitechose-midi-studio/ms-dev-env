from __future__ import annotations

from ms.output.console import ConsoleProtocol, Style
from ms.release.domain.dependency_readiness_models import (
    DependencyReadinessItem,
    DependencyReadinessReport,
    next_action_for_item,
)


def print_dependency_readiness_report(
    *, console: ConsoleProtocol, report: DependencyReadinessReport
) -> None:
    console.header("Dependency readiness")
    blockers = report.blockers
    if blockers:
        console.print(
            f"BLOCKED {report.blocker_count}/{len(report.items)} repo(s) need action "
            "before dependency promotion",
            Style.WARNING,
        )
        for item in blockers:
            _print_blocking_item(console=console, item=item)
        if report.ready_count:
            console.print(f"ready: {report.ready_count} repo(s) already clean/fetchable", Style.DIM)
        if len(blockers) > 1:
            first = blockers[0]
            action = next_action_for_item(first)
            console.print(f"start here: {first.repo} - {action.summary}", Style.WARNING)
            if action.command:
                console.print(f"cmd: {action.command}", Style.DIM)
        return

    console.success(f"READY {report.ready_count}/{len(report.items)} repo(s)")
    for item in report.items:
        if item.status == "ok":
            sha = item.sha[:12] if item.sha is not None else "unknown"
            console.success(f"{item.repo}: ready ({sha})")
            continue

        _print_blocking_item(console=console, item=item)


def _print_blocking_item(*, console: ConsoleProtocol, item: DependencyReadinessItem) -> None:
    console.print(f"{item.repo} ({item.status})", Style.WARNING)
    branch = item.branch or "detached"
    sha = item.sha[:12] if item.sha is not None else "unknown"
    console.print(f"where: {branch} @ {sha}", Style.DIM)
    summary, entries, hidden_count = _split_detail(item.detail)
    if summary:
        console.print(f"why: {summary}", Style.DIM)
    action = next_action_for_item(item)
    console.print(f"next: {action.summary}", Style.INFO)
    if action.command:
        console.print(f"cmd: {action.command}", Style.DIM)
    if entries:
        console.print("files:", Style.DIM)
        for entry in entries:
            console.print(f"  {entry}", Style.DIM)
        if hidden_count:
            console.print(f"  ... {hidden_count} more", Style.DIM)
    elif item.hint:
        console.print(f"hint: {item.hint}", Style.DIM)


def _split_detail(detail: str | None) -> tuple[str | None, tuple[str, ...], int]:
    if detail is None:
        return None, (), 0

    lines = [line.rstrip() for line in detail.splitlines() if line.strip()]
    if not lines:
        return None, (), 0

    summary = lines[0].strip()
    entries = tuple(line.strip() for line in lines[1:] if line.strip())
    limit = 5
    visible = entries[:limit]
    hidden_count = max(0, len(entries) - limit)
    return summary, visible, hidden_count
