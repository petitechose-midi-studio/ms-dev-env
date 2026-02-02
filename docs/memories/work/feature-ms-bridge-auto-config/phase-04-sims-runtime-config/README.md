# Phase 04: Sims Runtime Config (Ports Driven by config.toml)

Objective

- Remove port drift between `config.toml` and controller apps.
- Allow changing ports in `config.toml` without rebuilding hardcoded ports.

Approach

- Native sims: parse argv `--bridge-udp-port <port>` and use it for the remote UDP transport.
- WASM sims:
  - JS reads query param `bridgeWsPort` and passes argv `--bridge-ws-url ws://<host>:<port>`
  - C++ uses `--bridge-ws-url` when present.

Test

- Change `ports.controller.core_wasm` or `ports.controller.bitwig_wasm` in `config.toml`.
  - Run `ms web <app>` and verify the printed URL has the new `bridgeWsPort=` and the app connects.
- Change `ports.controller.bitwig_native` in `config.toml`.
  - Run `ms run bitwig` and verify it connects to the bridge.
