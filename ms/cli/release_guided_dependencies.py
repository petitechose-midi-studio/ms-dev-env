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
from ms.release.flow.core_dependency_pins import (
    CoreDependencyPinPlan,
    plan_core_dependency_pin_sync,
)
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
    return run_dependencies_release(
        workspace_root=workspace_root,
        console=console,
        notes_file=notes_file,
        watch=watch,
        dry_run=dry_run,
        promote=False,
        interactive=True,
    )


def run_dependencies_release(
    *,
    workspace_root: Path,
    console: ConsoleProtocol,
    notes_file: Path | None,
    watch: bool,
    dry_run: bool,
    promote: bool,
    interactive: bool,
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

    console.print("Checking pushed heads for every dependency repo", Style.DIM)
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
        console.print("Validating dev workspace targets", Style.DIM)
        dev_validated = validate_workspace_dev_targets(
            workspace_root=workspace_root,
            console=console,
        )
        if isinstance(dev_validated, Err):
            return dev_validated

    console.print("Planning core dependency promotion", Style.DIM)
    preview = plan_workspace_bom_sync(workspace_root=workspace_root)
    if isinstance(preview, Err):
        return preview

    core_pin_plan = plan_core_dependency_pin_sync(
        workspace_root=workspace_root,
        core_root=preview.value.state.core_root,
    )
    if isinstance(core_pin_plan, Err):
        return core_pin_plan

    if not preview.value.plan.requires_write and not core_pin_plan.value.requires_write:
        console.success("Core dependency pins already match the dev workspace")
        if dry_run:
            return Ok(None)
        return _maybe_watch_release_alignment(
            workspace_root=workspace_root,
            console=console,
            watch=watch,
            interactive=interactive,
            dry_run=False,
        )

    console.header("BOM promotion plan")
    console.print(
        f"version: {preview.value.plan.current_version} -> {preview.value.plan.next_version}",
        Style.DIM,
    )
    for item in preview.value.plan.items:
        if item.changed:
            before = item.from_sha[:12] if item.from_sha is not None else "unset"
            console.print(f"{item.repo}: {before} -> {item.to_sha[:12]}")
    _print_core_pin_plan(console=console, plan=core_pin_plan.value)

    if dry_run:
        console.success("dependency promotion dry-run completed")
        return Ok(None)

    if interactive:
        choice = to_guided_selection(
            _select_menu(
                title="Dependency Promotion",
                subtitle="Create and merge a core dependency PR from the validated dev workspace",
                options=[
                    MenuOption(
                        value="promote",
                        label="Promote dependencies",
                        detail="create, validate, and merge the core dependency PR",
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
    elif not promote:
        console.warning("dependency promotion planned; rerun with --promote to apply it")
        return Ok(None)

    allowed = ensure_core_release_permissions(
        workspace_root=workspace_root,
        console=console,
        require_write=True,
    )
    if isinstance(allowed, Err):
        return allowed

    console.print("Promoting dependencies through core PR", Style.DIM)
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

    return _maybe_watch_release_alignment(
        workspace_root=workspace_root,
        console=console,
        watch=watch,
        interactive=interactive,
        dry_run=False,
    )


def _maybe_watch_release_alignment(
    *,
    workspace_root: Path,
    console: ConsoleProtocol,
    watch: bool,
    interactive: bool,
    dry_run: bool,
) -> Result[None, ReleaseError]:
    should_watch = watch
    if interactive and not watch:
        watch_choice = to_guided_selection(
            _select_menu(
                title="Release Alignment",
                subtitle="Run and watch the deterministic release-alignment workflow?",
                options=[
                    MenuOption(
                        value="watch",
                        label="Watch Release Alignment",
                        detail="dispatch the workflow and wait for completion",
                    ),
                    MenuOption(
                        value="skip",
                        label="Skip watch",
                        detail="finish without release-alignment watch",
                    ),
                ],
                initial_index=0,
                allow_back=False,
            )
        )
        if watch_choice.action == "cancel":
            return Err(
                ReleaseError(
                    kind="invalid_input",
                    message="release alignment watch cancelled",
                )
            )
        should_watch = watch_choice.value == "watch"

    if not should_watch:
        return Ok(None)

    dispatched = dispatch_release_alignment_workflow(
        workspace_root=workspace_root,
        build_wasm=False,
        console=console,
        dry_run=dry_run,
    )
    if isinstance(dispatched, Err):
        return dispatched
    watched = watch_run(
        workspace_root=workspace_root,
        run_id=dispatched.value.id,
        repo_slug=MS_REPO_SLUG,
        console=console,
        dry_run=dry_run,
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


def _print_core_pin_plan(*, console: ConsoleProtocol, plan: CoreDependencyPinPlan) -> None:
    changed = [item for item in plan.items if item.changed]
    if not changed:
        return
    console.header("Core CI/runtime pin plan")
    for item in changed:
        before = item.from_sha[:12] if item.from_sha is not None else "unset"
        console.print(f"{item.key}: {before} -> {item.to_sha[:12]}")
