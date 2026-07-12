from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ms.core.result import Err, Ok, Result
from ms.release.domain.dependency_graph_models import ReleaseGraph
from ms.release.domain.open_control_models import BomPromotionPlan
from ms.release.errors import ReleaseError
from ms.release.flow.bom import sync_bom_files
from ms.release.flow.bom_workflow import plan_workspace_bom_sync
from ms.release.flow.consumer_dependency_pins import (
    ConsumerDependencyPinPlan,
    plan_consumer_dependency_pin_sync,
    sync_consumer_dependency_pin_plan,
)
from ms.release.flow.core_dependency_pins import (
    CoreDependencyPinPlan,
    plan_core_dependency_pin_sync,
    sync_core_dependency_pin_plan,
)


@dataclass(frozen=True, slots=True)
class DependencyPinPreparationPlan:
    consumer_id: str
    bom: BomPromotionPlan | None = None
    core: CoreDependencyPinPlan | None = None
    consumer: ConsumerDependencyPinPlan | None = None

    @property
    def requires_write(self) -> bool:
        return any(
            plan is not None and plan.requires_write
            for plan in (self.bom, self.core, self.consumer)
        )


@dataclass(frozen=True, slots=True)
class DependencyPinPreparationResult:
    plan: DependencyPinPreparationPlan
    written: tuple[Path, ...]


def plan_dependency_pin_preparation(
    *, workspace_root: Path, graph: ReleaseGraph, consumer_id: str
) -> Result[DependencyPinPreparationPlan, ReleaseError]:
    if consumer_id not in graph.by_id():
        return Err(
            ReleaseError(kind="invalid_input", message=f"unknown release graph node: {consumer_id}")
        )

    if consumer_id != "core":
        consumer = plan_consumer_dependency_pin_sync(
            workspace_root=workspace_root,
            graph=graph,
            consumer_id=consumer_id,
        )
        if isinstance(consumer, Err):
            return consumer
        return Ok(DependencyPinPreparationPlan(consumer_id=consumer_id, consumer=consumer.value))

    bom = plan_workspace_bom_sync(workspace_root=workspace_root)
    if isinstance(bom, Err):
        return bom
    core = plan_core_dependency_pin_sync(workspace_root=workspace_root, source="workspace")
    if isinstance(core, Err):
        return core
    return Ok(
        DependencyPinPreparationPlan(
            consumer_id=consumer_id,
            bom=bom.value.plan,
            core=core.value,
        )
    )


def apply_dependency_pin_preparation(
    *, workspace_root: Path, graph: ReleaseGraph, plan: DependencyPinPreparationPlan
) -> Result[DependencyPinPreparationResult, ReleaseError]:
    written: list[Path] = []
    if plan.bom is not None and plan.bom.requires_write:
        synced_bom = sync_bom_files(
            core_root=workspace_root / "midi-studio" / "core",
            plan=plan.bom,
        )
        if isinstance(synced_bom, Err):
            return synced_bom
        written.extend(synced_bom.value)
    if plan.core is not None and plan.core.requires_write:
        synced_core = sync_core_dependency_pin_plan(plan=plan.core)
        if isinstance(synced_core, Err):
            return synced_core
        written.extend(synced_core.value.written)
    if plan.consumer is not None and plan.consumer.requires_write:
        synced_consumer = sync_consumer_dependency_pin_plan(graph=graph, plan=plan.consumer)
        if isinstance(synced_consumer, Err):
            return synced_consumer
        written.extend(synced_consumer.value.written)
    return Ok(DependencyPinPreparationResult(plan=plan, written=tuple(written)))


__all__ = [
    "DependencyPinPreparationPlan",
    "DependencyPinPreparationResult",
    "apply_dependency_pin_preparation",
    "plan_dependency_pin_preparation",
]
