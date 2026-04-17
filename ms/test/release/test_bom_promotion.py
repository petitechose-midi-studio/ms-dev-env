from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from ms.core.result import Ok
from ms.output.console import MockConsole
from ms.release.domain.open_control_models import (
    BomPromotionItem,
    BomPromotionPlan,
    BomRepoState,
    BomStateComparison,
    DerivedBomLock,
    OcSdkLock,
    OcSdkPin,
)
from ms.release.flow.bom_promotion import promote_open_control_bom
from ms.release.flow.bom_workflow import BomSyncPreview, BomSyncResult, BomWorkspaceState
from ms.release.flow.pr_outcome import PrMergeOutcome


def _workspace_state(*, root: Path, status: str) -> BomWorkspaceState:
    pins = (
        OcSdkPin(repo="framework", sha="1" * 40),
        OcSdkPin(repo="note", sha="2" * 40),
        OcSdkPin(repo="hal-common", sha="3" * 40),
        OcSdkPin(repo="hal-teensy", sha="4" * 40),
        OcSdkPin(repo="ui-lvgl", sha="5" * 40),
        OcSdkPin(repo="ui-lvgl-components", sha="6" * 40),
    )
    repos = tuple(
        BomRepoState(
            repo=pin.repo,
            bom_sha=pin.sha,
            workspace_sha=pin.sha,
            derived_sha=(pin.sha if pin.repo in {"framework", "note"} else None),
            workspace_exists=True,
            workspace_dirty=False,
        )
        for pin in pins
    )
    return BomWorkspaceState(
        core_root=root,
        bom_lock=OcSdkLock(version="0.1.3", pins=pins),
        derived_lock=DerivedBomLock(
            source="oc-native-sdk.ini",
            pins=pins[:2],
            expected_repos=("framework", "note"),
        ),
        comparison=BomStateComparison(repos=repos, status=status, blockers=()),
    )


def test_promote_open_control_bom_returns_already_merged_when_no_write_needed(
    monkeypatch, tmp_path: Path
) -> None:
    import ms.release.flow.bom_promotion as promotion

    preview = BomSyncPreview(
        state=_workspace_state(root=tmp_path / "core", status="aligned"),
        plan=BomPromotionPlan(
            source="workspace",
            current_version="0.1.3",
            next_version="0.1.3",
            items=(
                BomPromotionItem(
                    repo="framework",
                    from_sha="1" * 40,
                    to_sha="1" * 40,
                    changed=False,
                ),
            ),
            requires_write=False,
        ),
    )

    monkeypatch.setattr(
        promotion,
        "ensure_core_repo",
        lambda **_: Ok(SimpleNamespace(root=tmp_path / "core")),
    )
    monkeypatch.setattr(promotion, "ensure_clean_core_repo", lambda **_: Ok(None))
    monkeypatch.setattr(promotion, "core_checkout_main_and_pull", lambda **_: Ok(None))
    monkeypatch.setattr(promotion, "plan_workspace_bom_sync", lambda **_: Ok(preview))
    monkeypatch.setattr(promotion, "get_ref_head_sha", lambda **_: Ok("a" * 40))
    monkeypatch.setattr(
        promotion,
        "core_create_branch",
        lambda **_: (_ for _ in ()).throw(AssertionError("should not create branch")),
    )

    result = promote_open_control_bom(
        workspace_root=tmp_path,
        console=MockConsole(),
        dry_run=False,
    )

    assert isinstance(result, Ok)
    assert result.value.pr.kind == "already_merged"
    assert result.value.merged_core_sha == "a" * 40


def test_promote_open_control_bom_creates_and_merges_core_pr(
    monkeypatch, tmp_path: Path
) -> None:
    import ms.release.flow.bom_promotion as promotion

    core_root = tmp_path / "midi-studio" / "core"
    written = (core_root / "oc-sdk.ini", core_root / "oc-native-sdk.ini")
    preview = BomSyncPreview(
        state=_workspace_state(root=core_root, status="promotion_required"),
        plan=BomPromotionPlan(
            source="workspace",
            current_version="0.1.3",
            next_version="0.1.4",
            items=(
                BomPromotionItem(
                    repo="framework",
                    from_sha="1" * 40,
                    to_sha="9" * 40,
                    changed=True,
                ),
            ),
            requires_write=True,
        ),
    )
    synced = BomSyncResult(
        before=preview.state,
        plan=preview.plan,
        written=written,
        after=preview.state,
        validations=(),
    )

    calls: list[str] = []
    monkeypatch.setattr(
        promotion,
        "ensure_core_repo",
        lambda **_: Ok(SimpleNamespace(root=core_root)),
    )
    monkeypatch.setattr(
        promotion,
        "ensure_clean_core_repo",
        lambda **_: calls.append("clean") or Ok(None),
    )
    monkeypatch.setattr(
        promotion,
        "core_checkout_main_and_pull",
        lambda **_: calls.append("pull") or Ok(None),
    )
    monkeypatch.setattr(promotion, "plan_workspace_bom_sync", lambda **_: Ok(preview))
    monkeypatch.setattr(
        promotion,
        "core_create_branch",
        lambda **kwargs: calls.append(f"branch:{kwargs['branch']}") or Ok(None),
    )
    monkeypatch.setattr(
        promotion,
        "sync_workspace_bom",
        lambda **_: calls.append("sync") or Ok(synced),
    )
    monkeypatch.setattr(
        promotion,
        "core_commit_and_push",
        lambda **kwargs: calls.append(f"commit:{kwargs['message']}") or Ok("b" * 40),
    )
    monkeypatch.setattr(
        promotion,
        "core_open_pr",
        lambda **kwargs: calls.append(f"pr:{kwargs['title']}") or Ok("https://example/pr/42"),
    )
    monkeypatch.setattr(
        promotion,
        "core_merge_pr",
        lambda **_: calls.append("merge") or Ok(None),
    )
    monkeypatch.setattr(
        promotion,
        "get_ref_head_sha",
        lambda **_: calls.append("head") or Ok("c" * 40),
    )

    result = promote_open_control_bom(
        workspace_root=tmp_path,
        console=MockConsole(),
        dry_run=False,
    )

    assert isinstance(result, Ok)
    assert result.value.pr == PrMergeOutcome(
        kind="merged_pr",
        url="https://example/pr/42",
        label="https://example/pr/42",
    )
    assert result.value.merged_core_sha == "c" * 40
    assert calls == [
        "clean",
        "pull",
        "branch:release/oc-sdk-v0.1.4-99999999",
        "sync",
        "commit:release(core): promote OpenControl BOM to v0.1.4",
        "pr:release(core): promote OpenControl BOM to v0.1.4",
        "merge",
        "head",
        "pull",
    ]
