from __future__ import annotations

from pathlib import Path

import pytest
import typer

from ms.cli.context import CLIContext
from ms.core.errors import ErrorCode
from ms.core.result import Ok
from ms.core.workspace import Workspace
from ms.output.console import MockConsole
from ms.platform.detection import detect
from ms.release.domain.open_control_models import (
    BomComparisonStatus,
    BomPromotionItem,
    BomPromotionPlan,
    BomRepoState,
    BomStateComparison,
    DerivedBomLock,
    OcSdkLock,
    OcSdkPin,
)
from ms.release.flow.bom_workflow import (
    BomSyncPreview,
    BomSyncResult,
    BomValidationTarget,
    BomWorkspaceState,
)


def _ctx(tmp_path: Path, console: MockConsole) -> CLIContext:
    (tmp_path / ".ms-workspace").write_text("", encoding="utf-8")
    return CLIContext(
        workspace=Workspace(root=tmp_path),
        platform=detect(),
        config=None,
        console=console,
    )


def _state(*, status: BomComparisonStatus) -> BomWorkspaceState:
    pins = (
        OcSdkPin(repo="framework", sha="1" * 40),
        OcSdkPin(repo="note", sha="2" * 40),
        OcSdkPin(repo="hal-common", sha="3" * 40),
        OcSdkPin(repo="hal-teensy", sha="4" * 40),
        OcSdkPin(repo="ui-lvgl", sha="5" * 40),
        OcSdkPin(repo="ui-lvgl-components", sha="6" * 40),
    )
    repos = (
        BomRepoState(
            repo="framework",
            bom_sha="1" * 40,
            workspace_sha=("9" * 40 if status != "aligned" else "1" * 40),
            derived_sha="1" * 40,
            workspace_exists=True,
            workspace_dirty=False,
        ),
        BomRepoState(
            repo="note",
            bom_sha="2" * 40,
            workspace_sha="2" * 40,
            derived_sha="2" * 40,
            workspace_exists=True,
            workspace_dirty=False,
        ),
        BomRepoState(
            repo="hal-common",
            bom_sha="3" * 40,
            workspace_sha="3" * 40,
            derived_sha=None,
            workspace_exists=True,
            workspace_dirty=False,
        ),
        BomRepoState(
            repo="hal-teensy",
            bom_sha="4" * 40,
            workspace_sha="4" * 40,
            derived_sha=None,
            workspace_exists=True,
            workspace_dirty=False,
        ),
        BomRepoState(
            repo="ui-lvgl",
            bom_sha="5" * 40,
            workspace_sha="5" * 40,
            derived_sha=None,
            workspace_exists=True,
            workspace_dirty=False,
        ),
        BomRepoState(
            repo="ui-lvgl-components",
            bom_sha="6" * 40,
            workspace_sha="6" * 40,
            derived_sha=None,
            workspace_exists=True,
            workspace_dirty=False,
        ),
    )
    blockers = ("native_ci BOM unavailable",) if status == "blocked" else ()
    return BomWorkspaceState(
        core_root=Path("/tmp/core"),
        bom_lock=OcSdkLock(version="0.1.3", pins=pins),
        derived_lock=DerivedBomLock(
            source="oc-native-sdk.ini",
            pins=(pins[0], pins[1]),
            expected_repos=("framework", "note"),
        ),
        comparison=BomStateComparison(
            repos=repos,
            status=status,
            blockers=blockers,
        ),
    )


def test_verify_bom_cmd_succeeds_when_aligned(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import ms.cli.commands.release_bom_commands as bom_cmd

    console = MockConsole()

    def fake_verify_workspace_bom_files(**_: object) -> Ok[BomWorkspaceState]:
        return Ok(_state(status="aligned"))

    monkeypatch.setattr(bom_cmd, "build_context", lambda: _ctx(tmp_path, console))
    monkeypatch.setattr(bom_cmd, "verify_workspace_bom_files", fake_verify_workspace_bom_files)

    bom_cmd.verify_bom_cmd()

    assert any("OpenControl BOM verified" in message for message in console.messages)


def test_verify_bom_cmd_exits_when_not_aligned(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import ms.cli.commands.release_bom_commands as bom_cmd

    console = MockConsole()

    def fake_verify_workspace_bom_files(**_: object) -> Ok[BomWorkspaceState]:
        return Ok(_state(status="promotion_required"))

    monkeypatch.setattr(bom_cmd, "build_context", lambda: _ctx(tmp_path, console))
    monkeypatch.setattr(bom_cmd, "verify_workspace_bom_files", fake_verify_workspace_bom_files)

    with pytest.raises(typer.Exit) as exc:
        bom_cmd.verify_bom_cmd()

    assert exc.value.exit_code == int(ErrorCode.USER_ERROR)


def test_validate_bom_targets_cmd_succeeds_when_aligned(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import ms.cli.commands.release_bom_commands as bom_cmd

    console = MockConsole()

    def fake_verify_workspace_bom_files(**_: object) -> Ok[BomWorkspaceState]:
        return Ok(_state(status="aligned"))

    def fake_validate_workspace_bom_targets(
        **_: object,
    ) -> Ok[tuple[BomValidationTarget, ...]]:
        return Ok(
            (
                BomValidationTarget(
                    key="core-release",
                    label="core release",
                    cwd=tmp_path,
                    command=("python", "-m", "platformio", "run", "-e", "release"),
                ),
            )
        )

    monkeypatch.setattr(bom_cmd, "build_context", lambda: _ctx(tmp_path, console))
    monkeypatch.setattr(bom_cmd, "verify_workspace_bom_files", fake_verify_workspace_bom_files)
    monkeypatch.setattr(
        bom_cmd,
        "validate_workspace_bom_targets",
        fake_validate_workspace_bom_targets,
    )

    bom_cmd.validate_bom_targets_cmd()

    assert any("core release" in message for message in console.messages)
    assert any("verify-bom:" in message for message in console.messages)
    assert any("validate-targets:" in message for message in console.messages)
    assert any("OpenControl BOM targets validated" in message for message in console.messages)


def test_sync_bom_cmd_preview_warns_when_write_needed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import ms.cli.commands.release_bom_commands as bom_cmd

    console = MockConsole()
    state = _state(status="promotion_required")
    preview = BomSyncPreview(
        state=state,
        plan=BomPromotionPlan(
            source="workspace",
            current_version="0.1.2",
            next_version="0.1.3",
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

    def fake_plan_workspace_bom_sync(**_: object) -> Ok[BomSyncPreview]:
        return Ok(preview)

    monkeypatch.setattr(bom_cmd, "build_context", lambda: _ctx(tmp_path, console))
    monkeypatch.setattr(bom_cmd, "plan_workspace_bom_sync", fake_plan_workspace_bom_sync)

    bom_cmd.sync_bom_cmd(write=False, validate_targets=False)

    assert any("rerun with --write" in message for message in console.messages)


def test_sync_bom_cmd_write_runs_sync(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import ms.cli.commands.release_bom_commands as bom_cmd

    console = MockConsole()
    state = _state(status="aligned")
    preview = BomSyncPreview(
        state=state,
        plan=BomPromotionPlan(
            source="workspace",
            current_version="0.1.3",
            next_version="0.1.3",
            items=(),
            requires_write=False,
        ),
    )
    result = BomSyncResult(
        before=state,
        plan=preview.plan,
        written=(tmp_path / "midi-studio" / "core" / "oc-sdk.ini",),
        after=state,
        validations=(
            BomValidationTarget(
                key="core-release",
                label="core release",
                cwd=tmp_path,
                command=("python", "-m", "platformio", "run", "-e", "release"),
            ),
        ),
    )

    def fake_plan_workspace_bom_sync(**_: object) -> Ok[BomSyncPreview]:
        return Ok(preview)

    def fake_sync_workspace_bom(**_: object) -> Ok[BomSyncResult]:
        return Ok(result)

    monkeypatch.setattr(bom_cmd, "build_context", lambda: _ctx(tmp_path, console))
    monkeypatch.setattr(bom_cmd, "plan_workspace_bom_sync", fake_plan_workspace_bom_sync)
    monkeypatch.setattr(bom_cmd, "sync_workspace_bom", fake_sync_workspace_bom)

    bom_cmd.sync_bom_cmd(write=True, validate_targets=True)

    assert any("OpenControl BOM synchronized" in message for message in console.messages)
