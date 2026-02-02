# Phase 03: ms Orchestration (Auto Bridge)

Objective

- `ms web <app>` and `ms run <app>` always start a headless bridge configured from `config.toml`.
- Warn on collisions and reuse when safe.

Design

- Single implementation point: `BuildService`.
- Small helper service:
  - computes ports from `Config`
  - spawns `oc-bridge --headless ...`
  - readiness check
  - shutdown cleanup

Test

- `uv run ms web core`:
  - starts bridge (WS `ports.controller.core_wasm` -> host UDP `ports.wasm`)
  - serves wasm html
- `uv run ms run bitwig`:
  - starts bridge (UDP `ports.controller.bitwig_native` -> host UDP `ports.native`)
  - launches native app
