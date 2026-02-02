from __future__ import annotations

from ms.core.config import Config
from ms.services.bridge_headless import spec_for


def test_spec_for_core_native_defaults() -> None:
    cfg = Config()
    spec = spec_for(cfg, app_name="core", mode="native")
    assert spec.mode == "native"
    assert spec.controller == "udp"
    assert spec.controller_port == 8000
    assert spec.host_udp_port == 9001


def test_spec_for_bitwig_native_defaults() -> None:
    cfg = Config()
    spec = spec_for(cfg, app_name="bitwig", mode="native")
    assert spec.controller == "udp"
    assert spec.controller_port == 8001
    assert spec.host_udp_port == 9001


def test_spec_for_core_wasm_defaults() -> None:
    cfg = Config()
    spec = spec_for(cfg, app_name="core", mode="wasm")
    assert spec.mode == "wasm"
    assert spec.controller == "ws"
    assert spec.controller_port == 8100
    assert spec.host_udp_port == 9002


def test_spec_for_bitwig_wasm_defaults() -> None:
    cfg = Config()
    spec = spec_for(cfg, app_name="bitwig", mode="wasm")
    assert spec.controller == "ws"
    assert spec.controller_port == 8101
    assert spec.host_udp_port == 9002
