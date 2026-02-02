# Feature: ms Auto Bridge + Runtime Port Config

Goal: make the dev UX deterministic.

- `ms web <app>` and `ms run <app>` always start the right `oc-bridge` headless subprocess for the requested mode (wasm/native).
- Ports are driven by `config.toml` and propagated end-to-end (ms -> bridge subprocess -> controller apps).
- The permanent `oc-bridge` service (hardware/serial) continues to run independently.

Scope

- Apps: `core` and `bitwig`.
- Modes:
  - hardware: controller=serial (service), host=UDP `ports.hardware`
  - native sim: controller=UDP `ports.controller.*_native`, host=UDP `ports.native`
  - wasm sim: controller=WS `ports.controller.*_wasm`, host=UDP `ports.wasm`

Design constraints

- Avoid duplicated "port mapping" logic.
- No silent failure: if bridge can't be started and no compatible instance is detected, don't launch the app.
- Allow common dev combos (hardware + 1 native + 1 wasm). If a mode is already active, print a warning and reuse when safe.

Phases

- Phase 01: audit + plan (this document set)
- Phase 02: oc-bridge: avoid IPC collisions; print useful headless logs
- Phase 03: ms: auto-spawn bridge subprocesses (native+wasm) with config.toml ports
- Phase 04: sims: runtime-configurable remote endpoints (native argv + wasm query/argv)
- Phase 05: polish + docs + legacy cleanup
