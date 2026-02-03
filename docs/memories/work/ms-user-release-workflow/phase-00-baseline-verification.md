# Phase 00: Baseline Verification + Repo Inventory

Status: DONE

## Goal

Verify that the current codebase and recent commits match the assumptions in `README.md`.
If anything differs, update the plan before implementing new work.

## Why This Exists

This workflow spans multiple repos (midi-studio, open-control, ms-manager, distribution).
Before adding new infrastructure, we must confirm:

- the installer-facing JSON contract is stable enough to build a GUI on top
- the bridge/service behaviors match the chosen strategy
- the build inputs/outputs are well understood

## Tasks

1) Verify loader JSON contract (required dependency)

- Run:
  - `midi-studio-loader.exe list --json`
  - `midi-studio-loader.exe doctor --json`
  - `midi-studio-loader.exe flash <hex> --dry-run --json --json-progress none`
  - `midi-studio-loader.exe flash <hex> --device halfkay:NOT_A_DEVICE --json --json-progress none`
- Confirm:
  - `list --json` emits a single event `{schema,event:"list"}`.
  - `flash --dry-run` emits a `dry_run` event.
  - `flash` emits `operation_summary` even when `--json-progress none` (validate via a safe failure like `--device halfkay:NOT_A_DEVICE`).
  - `operation_summary` contains `exit_code`, `targets_*`, `bridge_*`, `blocks`, `retries`.
  - when `--json` is used: stdout is JSON-only (logs/progress go to stderr).

Also verify a critical safety invariant:
- Pick a target that requires bridge pausing (typically `serial:*`).
- Start a flash and interrupt it (user cancel / kill process / unplug).
- Confirm the bridge does not remain paused:
  - `oc-bridge ctl status` shows resumed/running.
  - if it ends up paused, treat as a must-fix before Phase 06.

2) Verify oc-bridge capabilities and gaps

- Run:
  - `oc-bridge --help`
  - `oc-bridge ctl --help`
  - `oc-bridge install --help`
- Confirm:
  - control plane exists (ctl pause/resume/status)
  - Windows service exists but uses hard-coded service name today
  - Linux service exists but uses hard-coded service name + installs a .desktop today

Also verify a critical upgrade detail:
- Linux systemd user install uses `current_exe()`; if `current/` is a symlink to `versions/<tag>`,
  ExecStart may be written with a versioned path. That breaks “switch current => restart service”.
  Record current behavior and treat it as a must-fix in Phase 03 (service exec path override).

3) Inventory what the end-user system will include (v1)

Record the exact “v1 payload set”, split into:

- Bootstrap installer payload (rarely changes):
  - `ms-manager` (GUI)
  - `ms-updater` (apply helper)

- Distribution payload (downloaded via signed manifest):
  - `midi-studio-loader` (firmware flashing)
  - `oc-bridge` + `bin/config/default.toml` + `bin/config/devices/teensy.toml`
  - Bitwig extension: `midi_studio.bwextension`
  - Firmware:
    - `default` (standalone)
    - `bitwig` (standalone + bitwig)

4) Freeze OS/arch matrix (v1)

- Windows x86_64
- macOS x86_64 + arm64
- Linux x86_64

5) Define install root + `current/` semantics per OS

- Windows: app in Program Files, payload+current in ProgramData, stable service path to `current/`.
- macOS: app in /Applications, payload+current in user Application Support.
- Linux: app user-level, payload+current in `~/.local/share/midi-studio`.

6) Decide and document “CI passed” meaning for nightly selection

- Define one canonical workflow name per repo (recommended: `CI`).
- Nightly selection rule:
  - choose latest commit on `main` that has a successful run of that workflow
  - skip nightly if any repo has no successful run
  - build distribution bundle; if it fails, publish nothing

## Exit Criteria

- All confirmations above are true, or the plan is updated to match reality.
- `README.md` baseline section remains accurate.
- The v1 payload set is clearly recorded.

## Results (recorded)

v1 payload set (recorded):

- Bootstrap installer payload:
  - `ms-manager` (GUI)
  - `ms-updater` (helper, used for atomic updates)

- Distribution payload:
  - `midi-studio-loader` (firmware flashing)
  - `oc-bridge` + config folder (must be under `bin/config/**` in bundles)
  - Bitwig extension: `midi_studio.bwextension`
  - Firmware (Teensy): `default` + `bitwig`

OS/arch matrix (v1):
- Windows x86_64
- macOS x86_64 + arm64
- Linux x86_64

Install roots + `current/` semantics (v1):
- Windows:
  - App: Program Files (installer)
  - Payload root (versions/current/state/logs): `C:\ProgramData\MIDI Studio\`
  - Bridge service exec path must point to stable `current/` (requires Phase 03 `--service-exec`)
- macOS:
  - App: `/Applications`
  - Payload root: `~/Library/Application Support/MIDI Studio/`
- Linux:
  - App: user-level
  - Payload root: `~/.local/share/midi-studio/`

Nightly selection “CI passed” meaning (v1):
- The release spec pins the required workflow file per repo (`required_ci_workflow_file`).
- Nightly selects the latest `main` commit that has a successful run of that workflow.
- If any required repo has no successful run: skip nightly.

## Tests

Quick checks (local):
- Run the commands listed in Tasks 1 and 2.

Full checks (local):
- `cargo test` in:
  - `midi-studio/loader`
  - `open-control/bridge`

## Notes (recorded)

- `flash --dry-run` currently ends at `dry_run` (no `operation_summary`). For `operation_summary` verification without flashing, use a safe failure (`--device halfkay:NOT_A_DEVICE`).
- On Windows in ms-dev-env today, oc-bridge service id is `OpenControlBridge` and the binary is `bin/bridge/oc-bridge.exe`.
 - Bundle layout requirement: oc-bridge discovers config next to the executable, so distribution bundles must place config under `bin/config/**`.
