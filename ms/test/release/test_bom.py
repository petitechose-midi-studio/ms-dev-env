from __future__ import annotations

from pathlib import Path

from ms.core.result import Err, Ok
from ms.release.domain.open_control_models import (
    OPEN_CONTROL_BOM_REPOS,
    OPEN_CONTROL_NATIVE_CI_REPOS,
    DerivedBomLock,
    OcSdkLock,
    OcSdkPin,
    OpenControlRepoState,
)
from ms.release.flow.bom import (
    collect_workspace_bom_state,
    compare_bom_state,
    load_bom_lock_from_file,
    load_native_ci_bom,
    plan_bom_promotion,
    sync_bom_files,
    verify_bom_files,
)


def _lock(version: str, sha_prefix: str) -> OcSdkLock:
    pins = tuple(
        OcSdkPin(repo=repo, sha=f"{sha_prefix}{index:039x}")
        for index, repo in enumerate(OPEN_CONTROL_BOM_REPOS, start=1)
    )
    return OcSdkLock(version=version, pins=pins)


def _workspace_repos(lock: OcSdkLock, *, dirty_repo: str | None = None) -> tuple[OpenControlRepoState, ...]:
    pins = lock.pins_by_repo()
    return tuple(
        OpenControlRepoState(
            repo=repo,
            path=Path(f"/tmp/{repo}"),
            exists=True,
            head_sha=pins[repo],
            dirty=(repo == dirty_repo),
        )
        for repo in OPEN_CONTROL_BOM_REPOS
    )


def _derived_from_lock(lock: OcSdkLock, *, missing: set[str] | None = None) -> DerivedBomLock:
    missing = missing or set()
    pins = tuple(
        pin
        for pin in lock.pins
        if pin.repo in OPEN_CONTROL_NATIVE_CI_REPOS and pin.repo not in missing
    )
    return DerivedBomLock(
        source="platformio.ini",
        pins=pins,
        expected_repos=OPEN_CONTROL_NATIVE_CI_REPOS,
    )


def test_collect_workspace_bom_state_includes_note(tmp_path: Path) -> None:
    workspace_root = tmp_path / "ws"
    for repo in OPEN_CONTROL_BOM_REPOS:
        repo_root = workspace_root / "open-control" / repo
        repo_root.mkdir(parents=True)
        (repo_root / ".git").write_text("gitdir: nowhere\n", encoding="utf-8")

    repos = collect_workspace_bom_state(workspace_root=workspace_root)
    assert isinstance(repos, Ok)
    assert tuple(repo.repo for repo in repos.value) == OPEN_CONTROL_BOM_REPOS


def test_load_bom_lock_from_file_parses_note_pin(tmp_path: Path) -> None:
    lock_file = tmp_path / "oc-sdk.ini"
    lock_file.write_text(
        (
            "[oc_sdk]\n"
            "version = 0.1.2\n\n"
            "[oc_sdk_deps]\n"
            "lib_deps =\n"
            "    oc-framework=https://github.com/open-control/framework.git#"
            "1111111111111111111111111111111111111111\n"
            "    oc-note=https://github.com/open-control/note.git#"
            "2222222222222222222222222222222222222222\n"
            "    oc-hal-common=https://github.com/open-control/hal-common.git#"
            "3333333333333333333333333333333333333333\n"
            "    oc-hal-teensy=https://github.com/open-control/hal-teensy.git#"
            "4444444444444444444444444444444444444444\n"
            "    oc-ui-lvgl=https://github.com/open-control/ui-lvgl.git#"
            "5555555555555555555555555555555555555555\n"
            "    oc-ui-lvgl-components=https://github.com/open-control/ui-lvgl-components.git#"
            "6666666666666666666666666666666666666666\n"
        ),
        encoding="utf-8",
    )

    parsed = load_bom_lock_from_file(path=lock_file)
    assert isinstance(parsed, Ok)
    assert parsed.value.pins_by_repo()["note"] == "2222222222222222222222222222222222222222"


def test_load_native_ci_bom_reads_platformio_native_ci_inline_pins(tmp_path: Path) -> None:
    core_root = tmp_path / "core"
    core_root.mkdir()
    (core_root / "platformio.ini").write_text(
        (
            "[platformio]\n"
            "default_envs = dev\n\n"
            "[env:native_ci]\n"
            "lib_deps =\n"
            "    oc-note=https://github.com/open-control/note.git#"
            "2222222222222222222222222222222222222222\n"
            "    oc-framework=https://github.com/open-control/framework.git#"
            "1111111111111111111111111111111111111111\n"
        ),
        encoding="utf-8",
    )

    derived = load_native_ci_bom(core_root=core_root)
    assert isinstance(derived, Ok)
    assert derived.value.pins_by_repo()["note"] == "2222222222222222222222222222222222222222"
    assert "framework" in derived.value.pins_by_repo()


def test_compare_bom_state_reports_blocked_when_derived_is_incomplete() -> None:
    lock = _lock("0.1.2", "a")
    comparison = compare_bom_state(
        bom_lock=lock,
        workspace_repos=_workspace_repos(lock),
        derived_lock=_derived_from_lock(lock, missing={"note"}),
    )

    assert comparison.status == "blocked"
    assert any("derived native_ci pin missing: note" == blocker for blocker in comparison.blockers)


def test_compare_bom_state_reports_promotion_required_on_workspace_drift() -> None:
    lock = _lock("0.1.2", "a")
    repos = list(_workspace_repos(lock))
    pins = lock.pins_by_repo()
    repos[1] = OpenControlRepoState(
        repo="note",
        path=Path("/tmp/note"),
        exists=True,
        head_sha="b" + pins["note"][1:],
        dirty=False,
    )

    comparison = compare_bom_state(
        bom_lock=lock,
        workspace_repos=tuple(repos),
        derived_lock=_derived_from_lock(lock),
    )

    assert comparison.status == "promotion_required"
    assert comparison.blockers == ()


def test_plan_bom_promotion_bumps_patch_and_includes_note() -> None:
    lock = _lock("0.1.2", "a")
    repos = list(_workspace_repos(lock))
    pins = lock.pins_by_repo()
    repos[1] = OpenControlRepoState(
        repo="note",
        path=Path("/tmp/note"),
        exists=True,
        head_sha="b" + pins["note"][1:],
        dirty=False,
    )

    plan = plan_bom_promotion(current_lock=lock, workspace_repos=tuple(repos))
    assert isinstance(plan, Ok)
    value = plan.value
    assert value.current_version == "0.1.2"
    assert value.next_version == "0.1.3"
    assert value.requires_write is True
    note_item = next(item for item in value.items if item.repo == "note")
    assert note_item.changed is True


def test_plan_bom_promotion_refuses_dirty_workspace_repo() -> None:
    lock = _lock("0.1.2", "a")
    plan = plan_bom_promotion(
        current_lock=lock,
        workspace_repos=_workspace_repos(lock, dirty_repo="note"),
    )

    assert isinstance(plan, Err)
    assert "dirty" in plan.error.message


def test_verify_bom_files_rejects_incomplete_native_ci_lock() -> None:
    lock = _lock("0.1.2", "a")
    result = verify_bom_files(
        bom_lock=lock,
        derived_lock=_derived_from_lock(lock, missing={"framework"}),
    )

    assert isinstance(result, Err)
    assert "missing pins" in result.error.message


def test_sync_bom_files_writes_canonical_and_derived_files(tmp_path: Path) -> None:
    core_root = tmp_path / "core"
    core_root.mkdir()

    lock = _lock("0.1.2", "a")
    plan = plan_bom_promotion(current_lock=lock, workspace_repos=_workspace_repos(lock))
    assert isinstance(plan, Ok)
    written = sync_bom_files(core_root=core_root, plan=plan.value)

    assert isinstance(written, Ok)
    assert tuple(path.name for path in written.value) == ("oc-sdk.ini", "oc-native-sdk.ini")
