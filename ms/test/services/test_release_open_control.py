from __future__ import annotations

from ms.core.result import Err, Ok
from ms.services.release.open_control import OC_SDK_LOCK_FILE, parse_oc_sdk_ini


def test_parse_oc_sdk_ini_ok() -> None:
    text = """;
[oc_sdk]
version = 0.1.0

[oc_sdk_deps]
lib_deps =
  oc-framework=https://github.com/open-control/framework.git#aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
  oc-hal-common=https://github.com/open-control/hal-common.git#bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb
  oc-hal-teensy=https://github.com/open-control/hal-teensy.git#cccccccccccccccccccccccccccccccccccccccc
  oc-ui-lvgl=https://github.com/open-control/ui-lvgl.git#dddddddddddddddddddddddddddddddddddddddd
  oc-ui-lvgl-components=https://github.com/open-control/ui-lvgl-components.git#eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee
"""
    parsed = parse_oc_sdk_ini(text=text)
    assert isinstance(parsed, Ok)
    assert parsed.value.version == "0.1.0"
    pins = parsed.value.pins_by_repo()
    assert pins["framework"] == "a" * 40
    assert pins["hal-common"] == "b" * 40
    assert pins["ui-lvgl-components"] == "e" * 40


def test_parse_oc_sdk_ini_rejects_missing_pins() -> None:
    text = """[oc_sdk]
version = 0.1.0

[oc_sdk_deps]
lib_deps =
  oc-framework=https://github.com/open-control/framework.git#aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
"""
    parsed = parse_oc_sdk_ini(text=text)
    assert isinstance(parsed, Err)
    assert parsed.error.kind == "invalid_input"
    assert OC_SDK_LOCK_FILE in (parsed.error.hint or OC_SDK_LOCK_FILE)
