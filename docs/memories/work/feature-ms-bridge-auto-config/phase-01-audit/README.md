# Phase 01: Audit + Action Plan

Objective

- Identify where ports are defined today.
- Identify where the bridge is (not) launched today.
- Define a minimal, testable plan to make `config.toml` authoritative.

Current state (key findings)

- Ports are defined in `config.toml` and typed in `ms/core/config.py`.
- Controller apps (C++):
  - WASM apps hardcode WS URLs (`ws://localhost:8100/8101`).
  - Native Bitwig hardcodes controller UDP port `8001`.
  - Native core currently has no remote transport.
- `ms web <app>` builds WASM + runs `python -m http.server` but does not start a bridge.
- `ms run <app>` builds native + runs the exe but does not start a bridge.
- `oc-bridge` headless supports the correct knobs already:
  - `--controller {udp|ws}`
  - `--controller-port <port>`
  - `--udp-port <host_udp_port>`
- `oc-bridge` currently starts the local control server on `127.0.0.1:7999` unconditionally, which conflicts with the permanent serial service.
- `oc-bridge` headless does not stream useful runtime logs to stdout (most useful logs are behind `log_tx`).

Requirements recap

- Hardware bridge service continues to work independently (serial).
- `ms` should spawn an additional headless bridge for dev, configured from `config.toml`.
- `config.toml` should drive ports end-to-end: bridge subprocess and controller apps.
- Allow common dev combo: hardware + 1 native + 1 wasm. If a mode is already active, warn on collision.

Plan (phased, testable)

Phase 02 (oc-bridge)

- Start the control plane (`7999`) only for `ControllerTransport::Serial`.
- Headless mode prints useful runtime logs to stdout (at least `LogKind::System`).

Test

- With the serial service running, start a headless WS bridge; it must not print a control-bind error.
- Headless output must show controller + host binding info and "Bridge started".

Phase 03 (ms orchestration)

- Add a small bridge subprocess manager that:
  - resolves/installs `oc-bridge`
  - spawns `oc-bridge --headless` with ports from `Config`
  - validates readiness (WS: TCP connect; UDP: process stays alive)
  - stops it on exit
- Integrate it into `BuildService.run_native()` and `BuildService.serve_wasm()` so it's automatic.

Test

- `uv run ms web core` starts a WS bridge on `ports.controller.core_wasm` and a host UDP on `ports.wasm`.
- `uv run ms run bitwig` starts a UDP bridge on `ports.controller.bitwig_native` and host UDP on `ports.native`.

Phase 04 (controller apps runtime config)

- WASM:
  - JS reads a query param (e.g. `bridgeWsPort`) and passes `--bridge-ws-url` to the WASM argv.
  - C++ uses `--bridge-ws-url` when present, else defaults.
- Native:
  - C++ parses `--bridge-udp-port` and uses it for the remote `UdpTransport`.
  - Core native adds remote transport for parity (even if features are minimal for now).
- `ms` passes the correct args (native) and prints the correct URL (wasm) so the config.toml values are authoritative.

Test

- Change `ports.controller.core_wasm` in `config.toml` and verify `ms web core` outputs a URL with the new port and the app connects.
- Change `ports.controller.bitwig_native` in `config.toml` and verify `ms run bitwig` uses the new port.

Phase 05 (polish)

- Fix misleading comments and docs around ports.
- Add lightweight Python unit tests around port mapping + URL generation.
