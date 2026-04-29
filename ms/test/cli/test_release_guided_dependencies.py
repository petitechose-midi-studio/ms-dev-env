from __future__ import annotations

from pathlib import Path

import pytest

from ms.core.result import Err, Ok
from ms.output.console import MockConsole
from ms.release.domain.dependency_graph_models import ReleaseGraph
from ms.release.domain.dependency_readiness_models import (
    DependencyReadinessItem,
    DependencyReadinessReport,
)
from ms.release.domain.open_control_models import BomPromotionPlan
from ms.release.errors import ReleaseError
from ms.release.flow.bom_promotion import BomPromotionResult
from ms.release.flow.bom_workflow import BomSyncPreview, BomWorkspaceState
from ms.release.flow.pr_outcome import PrMergeOutcome
from ms.release.infra.github.workflows import WorkflowRun


def _empty_graph() -> ReleaseGraph:
    return ReleaseGraph(nodes=())


def _preview(*, requires_write: bool) -> BomSyncPreview:
    return BomSyncPreview(
        state=BoomWorkspaceStateFactory.make(),
        plan=BomPromotionPlan(
            source="workspace",
            current_version="0.1.5",
            next_version=("0.1.6" if requires_write else "0.1.5"),
            items=(),
            requires_write=requires_write,
        ),
    )


class BoomWorkspaceStateFactory:
    @staticmethod
    def make() -> BomWorkspaceState:
        from ms.release.domain.open_control_models import (
            BomStateComparison,
            DerivedBomLock,
            OcSdkLock,
        )

        return BomWorkspaceState(
            core_root=Path("/tmp/core"),
            bom_lock=OcSdkLock(version="0.1.5", pins=()),
            derived_lock=DerivedBomLock(source="oc-native-sdk.ini", pins=(), expected_repos=()),
            comparison=BomStateComparison(repos=(), status="aligned", blockers=()),
        )


def test_guided_dependencies_blocks_on_readiness_report(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    import ms.cli.release_guided_dependencies as deps

    def fake_permission(**_: object) -> Ok[None]:
        return Ok(None)

    def fake_graph(**_: object) -> Ok[ReleaseGraph]:
        return Ok(_empty_graph())

    def fake_readiness(**_: object) -> DependencyReadinessReport:
        graph = _["graph"]
        if isinstance(graph, ReleaseGraph) and not graph.nodes:
            return DependencyReadinessReport(items=())
        return DependencyReadinessReport(
            items=(
                DependencyReadinessItem(
                    node_id="ms-dev-env",
                    repo="petitechose-midi-studio/ms-dev-env",
                    path=tmp_path,
                    status="dirty",
                    detail="unstaged=1\n  .M ms/foo.py",
                    hint="git status",
                ),
            )
        )

    monkeypatch.setattr(deps, "ensure_core_release_permissions", fake_permission)
    monkeypatch.setattr(deps, "load_release_graph", fake_graph)
    monkeypatch.setattr(deps, "assess_dependency_readiness", fake_readiness)

    console = MockConsole()
    result = deps.run_guided_dependencies_release(
        workspace_root=tmp_path,
        console=console,
        notes_file=None,
        watch=False,
        dry_run=True,
    )

    assert isinstance(result, Err)
    assert result.error.message == "dependency promotion blocked"
    assert result.error.hint is not None
    assert "petitechose-midi-studio/ms-dev-env" in result.error.hint
    assert "petitechose-midi-studio/ms-dev-env: dirty" in console.text
    assert ".M ms/foo.py" in console.text


def test_guided_dependencies_dry_run_prints_bom_plan_without_promoting(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    import ms.cli.release_guided_dependencies as deps

    promoted = {"called": False}

    def fake_permission(**_: object) -> Ok[None]:
        return Ok(None)

    def fake_graph(**_: object) -> Ok[ReleaseGraph]:
        return Ok(_empty_graph())

    def fake_readiness(**_: object) -> DependencyReadinessReport:
        return DependencyReadinessReport(items=())

    def fake_plan(**_: object) -> Ok[BomSyncPreview]:
        return Ok(_preview(requires_write=True))

    def fake_promote(**_: object):
        promoted["called"] = True
        return Err(ReleaseError(kind="repo_failed", message="should not run"))

    monkeypatch.setattr(deps, "ensure_core_release_permissions", fake_permission)
    monkeypatch.setattr(deps, "load_release_graph", fake_graph)
    monkeypatch.setattr(deps, "assess_dependency_readiness", fake_readiness)
    monkeypatch.setattr(deps, "plan_workspace_bom_sync", fake_plan)
    monkeypatch.setattr(deps, "promote_open_control_bom", fake_promote)

    console = MockConsole()
    result = deps.run_guided_dependencies_release(
        workspace_root=tmp_path,
        console=console,
        notes_file=None,
        watch=False,
        dry_run=True,
    )

    assert isinstance(result, Ok)
    assert not promoted["called"]
    assert "dependency promotion dry-run completed" in console.text


def test_guided_dependencies_watch_dispatches_and_watches_release_alignment(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    import ms.cli.release_guided_dependencies as deps

    calls: list[str] = []

    def fake_permission(**kwargs: object) -> Ok[None]:
        calls.append(f"permission:{kwargs.get('require_write')}")
        return Ok(None)

    def fake_graph(**_: object) -> Ok[ReleaseGraph]:
        return Ok(_empty_graph())

    def fake_readiness(**_: object) -> DependencyReadinessReport:
        return DependencyReadinessReport(items=())

    def fake_dev_validation(**_: object) -> Ok[tuple[object, ...]]:
        calls.append("dev")
        return Ok(())

    def fake_plan(**_: object) -> Ok[BomSyncPreview]:
        return Ok(_preview(requires_write=True))

    def fake_select_menu(**_: object):
        from ms.cli.selector import SelectorResult

        return SelectorResult(action="select", value="promote", index=0)

    def fake_promote(**_: object) -> Ok[BomPromotionResult]:
        calls.append("promote")
        return Ok(
            BomPromotionResult(
                pr=PrMergeOutcome(
                    kind="merged_pr",
                    url="https://example.test/pr/1",
                    label="https://example.test/pr/1",
                ),
                merged_core_sha="a" * 40,
                plan=BomPromotionPlan(
                    source="workspace",
                    current_version="0.1.5",
                    next_version="0.1.6",
                    items=(),
                    requires_write=True,
                ),
            )
        )

    def fake_dispatch(**_: object) -> Ok[WorkflowRun]:
        calls.append("dispatch")
        return Ok(WorkflowRun(id=42, url="https://example.test/run/42", request_id="req"))

    def fake_watch(**_: object) -> Ok[None]:
        calls.append("watch")
        return Ok(None)

    monkeypatch.setattr(deps, "ensure_core_release_permissions", fake_permission)
    monkeypatch.setattr(deps, "load_release_graph", fake_graph)
    monkeypatch.setattr(deps, "assess_dependency_readiness", fake_readiness)
    monkeypatch.setattr(deps, "validate_workspace_dev_targets", fake_dev_validation)
    monkeypatch.setattr(deps, "plan_workspace_bom_sync", fake_plan)
    monkeypatch.setattr(deps, "_select_menu", fake_select_menu)
    monkeypatch.setattr(deps, "promote_open_control_bom", fake_promote)
    monkeypatch.setattr(deps, "dispatch_release_alignment_workflow", fake_dispatch)
    monkeypatch.setattr(deps, "watch_run", fake_watch)

    console = MockConsole()
    result = deps.run_guided_dependencies_release(
        workspace_root=tmp_path,
        console=console,
        notes_file=None,
        watch=True,
        dry_run=False,
    )

    assert isinstance(result, Ok)
    assert calls == ["permission:False", "dev", "permission:True", "promote", "dispatch", "watch"]
    assert "Release Alignment passed" in console.text
