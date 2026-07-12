from pathlib import Path

from ms.core.result import Err, Ok
from ms.release.domain.dependency_graph_models import ReleaseGraph, ReleaseGraphNode
from ms.release.flow.consumer_dependency_pins import (
    plan_consumer_dependency_pin_sync,
    sync_consumer_dependency_pin_plan,
)


def _graph() -> ReleaseGraph:
    return ReleaseGraph(
        nodes=(
            ReleaseGraphNode(
                id="oc-framework",
                repo="open-control/framework",
                local_path="open-control/framework",
                role="bom_dependency",
            ),
            ReleaseGraphNode(
                id="oc-hal-common",
                repo="open-control/hal-common",
                local_path="open-control/hal-common",
                role="bom_dependency",
            ),
            ReleaseGraphNode(
                id="oc-hal-teensy",
                repo="open-control/hal-teensy",
                local_path="open-control/hal-teensy",
                role="bom_dependency",
                depends_on=("oc-framework", "oc-hal-common"),
            ),
        )
    )


def _write_platformio(path: Path, *, framework_sha: str, hal_common_sha: str) -> None:
    path.parent.mkdir(parents=True)
    path.write_text(
        f"""[env:dev]
lib_deps =
    framework=symlink://../framework

[env:release]
lib_deps =
    oc-framework=https://github.com/open-control/framework.git#{framework_sha}
    oc-hal-common=https://github.com/open-control/hal-common.git#{hal_common_sha}
    vendor/library@1.0.0
""",
        encoding="utf-8",
    )


def test_consumer_pin_sync_updates_only_release_dependency_shas(tmp_path: Path) -> None:
    platformio = tmp_path / "open-control" / "hal-teensy" / "platformio.ini"
    old_framework = "1" * 40
    old_hal_common = "2" * 40
    new_framework = "a" * 40
    new_hal_common = "b" * 40
    _write_platformio(
        platformio,
        framework_sha=old_framework,
        hal_common_sha=old_hal_common,
    )

    planned = plan_consumer_dependency_pin_sync(
        workspace_root=tmp_path,
        graph=_graph(),
        consumer_id="oc-hal-teensy",
        dependency_heads={
            "oc-framework": new_framework,
            "oc-hal-common": new_hal_common,
        },
    )

    assert isinstance(planned, Ok)
    assert planned.value.requires_write
    assert [item.dependency_id for item in planned.value.items] == [
        "oc-framework",
        "oc-hal-common",
    ]

    synced = sync_consumer_dependency_pin_plan(graph=_graph(), plan=planned.value)
    assert isinstance(synced, Ok)
    assert synced.value.written == (platformio,)

    content = platformio.read_text(encoding="utf-8")
    assert "framework=symlink://../framework" in content
    assert f"oc-framework=https://github.com/open-control/framework.git#{new_framework}" in content
    assert (
        f"oc-hal-common=https://github.com/open-control/hal-common.git#{new_hal_common}" in content
    )
    assert "vendor/library@1.0.0" in content


def test_consumer_pin_sync_bootstraps_unpinned_release_dependency(tmp_path: Path) -> None:
    platformio = tmp_path / "open-control" / "hal-teensy" / "platformio.ini"
    platformio.parent.mkdir(parents=True)
    platformio.write_text(
        """[env:release]
lib_deps =
    oc-framework=https://github.com/open-control/framework.git#1111111111111111111111111111111111111111
    https://github.com/open-control/hal-common
""",
        encoding="utf-8",
    )

    planned = plan_consumer_dependency_pin_sync(
        workspace_root=tmp_path,
        graph=_graph(),
        consumer_id="oc-hal-teensy",
        dependency_heads={
            "oc-framework": "a" * 40,
            "oc-hal-common": "b" * 40,
        },
    )

    assert isinstance(planned, Ok)
    hal_common = next(item for item in planned.value.items if item.dependency_id == "oc-hal-common")
    assert hal_common.from_sha is None
    assert hal_common.changed

    synced = sync_consumer_dependency_pin_plan(graph=_graph(), plan=planned.value)

    assert isinstance(synced, Ok)
    rendered = platformio.read_text(encoding="utf-8")
    assert (f"oc-hal-common=https://github.com/open-control/hal-common.git#{'b' * 40}") in rendered


def test_consumer_pin_plan_rejects_missing_release_dependency(tmp_path: Path) -> None:
    platformio = tmp_path / "open-control" / "hal-teensy" / "platformio.ini"
    platformio.parent.mkdir(parents=True)
    platformio.write_text(
        """[env:release]
lib_deps =
    oc-framework=https://github.com/open-control/framework.git#1111111111111111111111111111111111111111
""",
        encoding="utf-8",
    )

    planned = plan_consumer_dependency_pin_sync(
        workspace_root=tmp_path,
        graph=_graph(),
        consumer_id="oc-hal-teensy",
        dependency_heads={
            "oc-framework": "a" * 40,
            "oc-hal-common": "b" * 40,
        },
    )

    assert isinstance(planned, Err)
    assert planned.error.message == "missing release dependency for oc-hal-common"


def test_consumer_pin_plan_rejects_missing_dependency_head(tmp_path: Path) -> None:
    platformio = tmp_path / "open-control" / "hal-teensy" / "platformio.ini"
    _write_platformio(
        platformio,
        framework_sha="1" * 40,
        hal_common_sha="2" * 40,
    )

    planned = plan_consumer_dependency_pin_sync(
        workspace_root=tmp_path,
        graph=_graph(),
        consumer_id="oc-hal-teensy",
        dependency_heads={"oc-framework": "a" * 40},
    )

    assert isinstance(planned, Err)
    assert planned.error.message == "dependency head unavailable: oc-hal-common"


def test_consumer_pin_sync_does_not_touch_other_platformio_environments(
    tmp_path: Path,
) -> None:
    platformio = tmp_path / "open-control" / "hal-teensy" / "platformio.ini"
    old_framework = "1" * 40
    new_framework = "a" * 40
    _write_platformio(
        platformio,
        framework_sha=old_framework,
        hal_common_sha="2" * 40,
    )
    content = platformio.read_text(encoding="utf-8").replace(
        "framework=symlink://../framework",
        f"oc-framework=https://github.com/open-control/framework.git#{old_framework}",
    )
    platformio.write_text(content, encoding="utf-8")

    planned = plan_consumer_dependency_pin_sync(
        workspace_root=tmp_path,
        graph=_graph(),
        consumer_id="oc-hal-teensy",
        dependency_heads={
            "oc-framework": new_framework,
            "oc-hal-common": "2" * 40,
        },
    )
    assert isinstance(planned, Ok)

    synced = sync_consumer_dependency_pin_plan(graph=_graph(), plan=planned.value)

    assert isinstance(synced, Ok)
    rendered = platformio.read_text(encoding="utf-8")
    assert (
        rendered.count(
            f"oc-framework=https://github.com/open-control/framework.git#{old_framework}"
        )
        == 1
    )
    assert (
        rendered.count(
            f"oc-framework=https://github.com/open-control/framework.git#{new_framework}"
        )
        == 1
    )
