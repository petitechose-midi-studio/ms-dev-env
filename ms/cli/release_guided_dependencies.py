from __future__ import annotations

from pathlib import Path

from ms.cli.release_guided_common import to_guided_selection
from ms.cli.selector import SelectorOption, SelectorResult, select_one
from ms.core.result import Err, Ok, Result
from ms.output.console import ConsoleProtocol, Style
from ms.release.domain.config import MS_REPO_SLUG
from ms.release.domain.dependency_graph_models import ReleaseGraph, ReleaseGraphNode
from ms.release.domain.dependency_readiness_models import (
    DependencyReadinessItem,
    DependencyReadinessReport,
)
from ms.release.errors import ReleaseError
from ms.release.flow.bom_promotion import promote_open_control_bom
from ms.release.flow.bom_validation import validate_workspace_dev_targets
from ms.release.flow.bom_workflow import plan_workspace_bom_sync
from ms.release.flow.dependency_graph import load_release_graph
from ms.release.flow.dependency_readiness import assess_dependency_readiness
from ms.release.flow.guided.router import MenuOption
from ms.release.flow.permissions import ensure_core_release_permissions
from ms.release.infra.github.run_watch import watch_run
from ms.release.infra.github.workflows import dispatch_release_alignment_workflow
from ms.release.view.dependency_console import print_dependency_readiness_report


def _select_menu(
    *,
    title: str,
    subtitle: str,
    options: list[MenuOption[str]],
    initial_index: int,
    allow_back: bool,
) -> SelectorResult[str]:
    selector_options = [
        SelectorOption(value=option.value, label=option.label, detail=option.detail)
        for option in options
    ]
    return select_one(
        title=title,
        subtitle=subtitle,
        options=selector_options,
        initial_index=initial_index,
        allow_back=allow_back,
    )


def run_guided_dependencies_release(
    *,
    workspace_root: Path,
    console: ConsoleProtocol,
    notes_file: Path | None,
    watch: bool,
    dry_run: bool,
) -> Result[None, ReleaseError]:
    del notes_file

    auth = ensure_core_release_permissions(
        workspace_root=workspace_root,
        console=console,
        require_write=False,
    )
    if isinstance(auth, Err):
        return auth

    graph = load_release_graph()
    if isinstance(graph, Err):
        return graph

    readiness = _assess_guided_readiness(workspace_root=workspace_root, graph=graph.value)
    print_dependency_readiness_report(console=console, report=readiness)
    if not readiness.is_ready:
        blocker = _first_blocker(readiness.items)
        return Err(
            ReleaseError(
                kind="invalid_input",
                message="dependency promotion blocked",
                hint=_blocker_hint(blocker),
            )
        )

    if dry_run:
        console.print("dev validation skipped in dry-run", Style.DIM)
    else:
        dev_validated = validate_workspace_dev_targets(workspace_root=workspace_root)
        if isinstance(dev_validated, Err):
            return dev_validated
        for validation in dev_validated.value:
            console.success(validation.label)

    preview = plan_workspace_bom_sync(workspace_root=workspace_root)
    if isinstance(preview, Err):
        return preview
    if not preview.value.plan.requires_write:
        console.success("OpenControl BOM already matches the dev workspace")
        return Ok(None)

    console.header("BOM promotion plan")
    console.print(
        f"version: {preview.value.plan.current_version} -> {preview.value.plan.next_version}",
        Style.DIM,
    )
    for item in preview.value.plan.items:
        if item.changed:
            before = item.from_sha[:12] if item.from_sha is not None else "unset"
            console.print(f"{item.repo}: {before} -> {item.to_sha[:12]}")

    if dry_run:
        console.success("dependency promotion dry-run completed")
        return Ok(None)

    choice = to_guided_selection(
        _select_menu(
            title="Dependency Promotion",
            subtitle="Create and merge a core BOM PR from the validated dev workspace",
            options=[
                MenuOption(
                    value="promote",
                    label="Promote BOM",
                    detail="create, validate, and merge the core BOM PR",
                ),
                MenuOption(
                    value="cancel",
                    label="Cancel",
                    detail="leave the workspace unchanged",
                ),
            ],
            initial_index=0,
            allow_back=True,
        )
    )
    if choice.action in {"cancel", "back"} or choice.value == "cancel":
        return Err(ReleaseError(kind="invalid_input", message="dependency promotion cancelled"))

    allowed = ensure_core_release_permissions(
        workspace_root=workspace_root,
        console=console,
        require_write=True,
    )
    if isinstance(allowed, Err):
        return allowed

    promoted = promote_open_control_bom(
        workspace_root=workspace_root,
        console=console,
        dry_run=False,
    )
    if isinstance(promoted, Err):
        return promoted

    if promoted.value.pr.kind == "merged_pr":
        console.success(f"Core BOM PR merged: {promoted.value.pr.display()}")
    else:
        console.success(f"Core BOM already aligned on main: {promoted.value.merged_core_sha[:12]}")

    if watch:
        dispatched = dispatch_release_alignment_workflow(
            workspace_root=workspace_root,
            build_wasm=False,
            console=console,
            dry_run=False,
        )
        if isinstance(dispatched, Err):
            return dispatched
        watched = watch_run(
            workspace_root=workspace_root,
            run_id=dispatched.value.id,
            repo_slug=MS_REPO_SLUG,
            console=console,
            dry_run=False,
        )
        if isinstance(watched, Err):
            return watched
        console.success(f"Release Alignment passed: {dispatched.value.url}")
    return Ok(None)


def _assess_guided_readiness(
    *, workspace_root: Path, graph: ReleaseGraph
) -> DependencyReadinessReport:
    tooling_graph = ReleaseGraph(
        nodes=(
            ReleaseGraphNode(
                id="ms-dev-env",
                repo=MS_REPO_SLUG,
                local_path=".",
                role="release_producer",
            ),
        )
    )
    tooling = assess_dependency_readiness(workspace_root=workspace_root, graph=tooling_graph)
    dependencies = assess_dependency_readiness(workspace_root=workspace_root, graph=graph)
    return DependencyReadinessReport(items=(*tooling.items, *dependencies.items))


def _first_blocker(items: tuple[DependencyReadinessItem, ...]) -> DependencyReadinessItem:
    return next(item for item in items if item.is_blocking)


def _blocker_hint(item: DependencyReadinessItem) -> str:
    parts = [f"{item.repo}: {item.status}"]
    if item.detail:
        parts.append(item.detail)
    if item.hint:
        parts.append(item.hint)
    return "\n".join(parts)
