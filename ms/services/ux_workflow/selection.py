from __future__ import annotations

from pathlib import Path

from ms.core.result import Err, Ok, Result

from .models import (
    UxWorkflow,
    UxWorkflowCatalog,
    UxWorkflowError,
    UxWorkflowGroup,
    UxWorkflowNotFound,
    UxWorkflowSelectionAmbiguous,
)


def folder_prefix(path: str) -> str:
    normalized = _normalize_selection(path)
    return "" if normalized in {"", "."} else f"{normalized}/"


def _normalize_selection(selection: str) -> str:
    return selection.strip().replace("\\", "/").removeprefix("./").strip("/")


def groups(catalog: UxWorkflowCatalog, parent: str = "") -> tuple[UxWorkflowGroup, ...]:
    prefix = folder_prefix(parent)
    children: dict[str, int] = {}
    for workflow in catalog.workflows:
        if not workflow.relative_path.startswith(prefix):
            continue
        remainder = workflow.relative_path.removeprefix(prefix)
        child = remainder.split("/", 1)[0]
        if child.endswith(".ux"):
            continue
        path = f"{prefix}{child}".strip("/")
        children[path] = children.get(path, 0) + 1
    return tuple(
        UxWorkflowGroup(path=path, workflow_count=count)
        for path, count in sorted(children.items())
    )


def workflows_in(catalog: UxWorkflowCatalog, parent: str = "") -> tuple[UxWorkflow, ...]:
    prefix = folder_prefix(parent)
    return tuple(
        workflow for workflow in catalog.workflows
        if workflow.relative_path.startswith(prefix)
        and "/" not in workflow.relative_path.removeprefix(prefix)
    )


def count_selection(catalog: UxWorkflowCatalog, selection: str) -> int:
    resolved = resolve_selection(catalog, selection)
    return 0 if isinstance(resolved, Err) else len(resolved.value)


def resolve_selection(
    catalog: UxWorkflowCatalog, selection: str,
) -> Result[tuple[UxWorkflow, ...], UxWorkflowError]:
    normalized = _normalize_selection(selection)
    if normalized in {"", "."}:
        return Ok(catalog.workflows)
    direct = [
        workflow for workflow in catalog.workflows
        if workflow.relative_path == normalized or workflow.id == normalized
    ]
    if len(direct) == 1:
        return Ok((direct[0],))
    if len(direct) > 1:
        return Err(
            UxWorkflowSelectionAmbiguous(
                app_name=catalog.app.name, selection=selection,
                matches=tuple(workflow.relative_path for workflow in direct),
            )
        )
    prefix = folder_prefix(normalized)
    nested = tuple(
        workflow for workflow in catalog.workflows if workflow.relative_path.startswith(prefix)
    )
    if nested:
        return Ok(nested)
    basename = [
        workflow for workflow in catalog.workflows
        if Path(workflow.relative_path).name == normalized or Path(workflow.id).name == normalized
    ]
    if len(basename) == 1:
        return Ok((basename[0],))
    if len(basename) > 1:
        return Err(
            UxWorkflowSelectionAmbiguous(
                app_name=catalog.app.name, selection=selection,
                matches=tuple(workflow.relative_path for workflow in basename),
            )
        )
    return Err(UxWorkflowNotFound(app_name=catalog.app.name, selection=selection))


def selected_workflows(
    *, catalog: UxWorkflowCatalog, selections: tuple[str, ...], all_workflows: bool,
) -> Result[tuple[UxWorkflow, ...], UxWorkflowError]:
    if all_workflows:
        return Ok(catalog.workflows)
    if not selections:
        return Ok(())
    by_path: dict[str, UxWorkflow] = {}
    for selection in selections:
        resolved = resolve_selection(catalog, selection)
        if isinstance(resolved, Err):
            return resolved
        for workflow in resolved.value:
            by_path[workflow.relative_path] = workflow
    return Ok(tuple(by_path[path] for path in sorted(by_path)))
