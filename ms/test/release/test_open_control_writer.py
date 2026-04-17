from __future__ import annotations

from pathlib import Path

from ms.core.result import Err, Ok
from ms.release.domain.open_control_models import (
    OPEN_CONTROL_BOM_REPOS,
    OPEN_CONTROL_NATIVE_CI_REPOS,
    OcSdkPin,
)
from ms.release.infra.open_control import parse_oc_sdk_ini
from ms.release.infra.open_control_writer import (
    next_bom_version,
    parse_native_ci_sdk_ini,
    render_native_ci_sdk_ini,
    render_oc_sdk_ini,
    write_native_ci_sdk_ini,
    write_oc_sdk_ini,
)


def _pins() -> tuple[OcSdkPin, ...]:
    return tuple(
        OcSdkPin(repo=repo, sha=f"{index:040x}")
        for index, repo in enumerate(OPEN_CONTROL_BOM_REPOS, start=1)
    )


def test_next_bom_version_bumps_patch() -> None:
    assert next_bom_version("0.1.2") == "0.1.3"


def test_render_oc_sdk_ini_is_stable() -> None:
    rendered_a = render_oc_sdk_ini(version="0.1.2", pins=_pins())
    rendered_b = render_oc_sdk_ini(version="0.1.2", pins=_pins())

    assert rendered_a == rendered_b
    assert rendered_a.endswith("\n")
    assert "oc-note=https://github.com/open-control/note.git#" in rendered_a


def test_render_native_ci_sdk_ini_is_stable() -> None:
    rendered_a = render_native_ci_sdk_ini(pins=_pins())
    rendered_b = render_native_ci_sdk_ini(pins=_pins())

    assert rendered_a == rendered_b
    assert rendered_a.endswith("\n")
    assert "[oc_native_sdk_deps]" in rendered_a


def test_write_oc_sdk_ini_round_trips(tmp_path: Path) -> None:
    core_root = tmp_path / "core"
    core_root.mkdir()

    result = write_oc_sdk_ini(core_root=core_root, version="0.1.2", pins=_pins())
    assert isinstance(result, Ok)

    parsed = parse_oc_sdk_ini(text=(core_root / "oc-sdk.ini").read_text(encoding="utf-8"))
    assert isinstance(parsed, Ok)
    assert parsed.value.version == "0.1.2"
    assert parsed.value.pins_by_repo()["note"] == f"{2:040x}"


def test_write_native_ci_sdk_ini_round_trips(tmp_path: Path) -> None:
    core_root = tmp_path / "core"
    core_root.mkdir()

    result = write_native_ci_sdk_ini(core_root=core_root, pins=_pins())
    assert isinstance(result, Ok)

    content = (core_root / "oc-native-sdk.ini").read_text(encoding="utf-8")
    assert "oc-framework=https://github.com/open-control/framework.git#" in content
    assert "oc-note=https://github.com/open-control/note.git#" in content
    assert (
        "oc-ui-lvgl-components=https://github.com/open-control/ui-lvgl-components.git#"
        not in content
    )


def test_parse_native_ci_sdk_ini_requires_complete_pin_set() -> None:
    parsed = parse_native_ci_sdk_ini(
        text=(
            "[oc_native_sdk_deps]\n"
            "lib_deps =\n"
            "    oc-framework=https://github.com/open-control/framework.git#"
            "1111111111111111111111111111111111111111\n"
        )
    )

    assert isinstance(parsed, Err)


def test_render_native_ci_sdk_ini_only_contains_native_ci_repos() -> None:
    rendered = render_native_ci_sdk_ini(pins=_pins())

    for repo in OPEN_CONTROL_NATIVE_CI_REPOS:
        assert f"oc-{repo}=https://github.com/open-control/{repo}.git#" in rendered
    assert "oc-ui-lvgl=https://github.com/open-control/ui-lvgl.git#" not in rendered
