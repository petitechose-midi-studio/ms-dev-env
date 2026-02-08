from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from ms.output.console import ConsoleProtocol, Style
from ms.release.domain.diagnostics import RepoReadiness
from ms.release.domain.models import AppReleasePlan
from ms.release.domain.notes import AppPublishNotes


def print_app_auto_blockers(*, console: ConsoleProtocol, blockers: Sequence[RepoReadiness]) -> None:
    console.header("Auto Release Blocked")
    for readiness in blockers:
        repo = readiness.repo
        console.print(f"- {repo.id} ({repo.slug})", Style.DIM)
        if readiness.error is not None:
            console.error(readiness.error)
        elif readiness.status is not None and not readiness.status.is_clean:
            console.error("working tree is dirty")
        elif readiness.head_green is not True:
            console.error("remote HEAD is not green")


def print_app_plan(*, plan: AppReleasePlan, console: ConsoleProtocol) -> None:
    console.header("App Release Plan")
    console.print(f"channel: {plan.channel}")
    console.print(f"tag: {plan.tag}")
    console.print(f"version: {plan.version}")
    console.print("repos:")
    for pinned_repo in plan.pinned:
        console.print(f"- {pinned_repo.repo.id}: {pinned_repo.sha}")


def print_app_replay(
    *,
    plan: AppReleasePlan,
    console: ConsoleProtocol,
    plan_file: Path | None,
) -> None:
    repo_args = " ".join([f"--repo {p.repo.id}={p.sha}" for p in plan.pinned])
    console.newline()
    console.print("Replay:", Style.DIM)
    if plan_file is not None:
        console.print(f"ms release app publish --plan {plan_file}", Style.DIM)
    console.print(
        f"ms release app publish --channel {plan.channel} --tag {plan.tag} "
        f"--no-interactive {repo_args}",
        Style.DIM,
    )


def print_app_notes_attachment(*, console: ConsoleProtocol, notes: AppPublishNotes) -> None:
    if notes.source_path is None or notes.sha256 is None:
        return

    console.print(
        f"notes: attached from {notes.source_path} (sha256={notes.sha256[:12]})",
        Style.DIM,
    )
