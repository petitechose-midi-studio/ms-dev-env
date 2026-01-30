# Tracking: Teensy Uploader CLI Roadmap

This file tracks what we planned, what shipped, what is in progress, and what is next.
It is intentionally a changelog-style tracker (not a full design doc).

Last updated: 2026-01-30

## Current State (snapshot)

- Primary repo: `midi-studio/loader` (binary: `midi-studio-loader`)
- oc-bridge control plane now available on `127.0.0.1:7999` (pause/resume works)
- Windows perf (10 runs, `serial:COM6`, pause via `control`): ~7.0s p95, 0 retries
- Safety validated:
  - If bridge pause fails for a serial target, aborts before touching device
  - If device disconnects mid-flash, bridge resumes (not left paused)

## Roadmap Phases

### Phase 1 (Done): Core Flasher + Robust Windows HID Writes

Goal: reliable Teensy 4.1 HalfKay flashing, cross-platform, with Windows write stability.

Done:
- HalfKay HID protocol implementation (1024-byte blocks + 64-byte header, boot command)
- Intel HEX parsing with Teensy 4.x FlexSPI address mapping (0x6000_0000 -> 0x0000_0000)
- Skip blank blocks (except always write block 0)
- Per-block retry with reopen strategy
- Windows HID reliability: Win32 overlapped `WriteFile` backend + cancel/wait safety fix

### Phase 2 (Done): Multi-Device UX + Selection

Goal: safe-by-default when multiple targets exist.

Done:
- Target discovery for HalfKay + Serial (PJRC VID)
- Selectors: `serial:COMx`, `halfkay:<path>`, `index:n`, bare digits
- `--all` sequential flashing support
- Serial -> HalfKay association via delta snapshot/wait

### Phase 3 (Done): oc-bridge Coordination (Control Preferred)

Goal: safely free the serial port while flashing.

Done:
- Bridge control policy: `--bridge-method auto|control|service|process|none` (+ no-process fallback)
- IPC schema: loader sends `{schema:1, cmd:"..."}` to oc-bridge
- RAII guard ensures resume on drop
- Doctor output includes control + service + process diagnostics

Notes:
- We updated the running oc-bridge service binary so `ctl` works and `127.0.0.1:7999` responds.

### Phase 4 (In Progress): Safety Hardening + Contract Stability

Goal: make failure modes safe and predictable; keep stdout JSON-only when `--json`.

Done (in code, pending commit decisions):
- Abort early if bridge pause fails for serial targets (prevents risky partial operations)
- Treat "service not installed" as `pause_skipped` instead of `pause_failed`
- Added `--json-timestamps` (stable) to include `t_ms` (monotonic ms since process start)
- Added `--json-progress blocks|percent|none` to control per-block JSON verbosity
- Standardized target `kind` to `halfkay` (consistent across list/doctor/events)
- Added final JSON `operation_summary` event (per command) for easier installer parsing
- `list --json` now emits a single `{schema,event:"list"}` object (no more raw per-target lines)
- `target_detected` JSON now embeds a full `target` object (consistent with list/doctor target records)

Done (tests / harness):
- Removed temporary test hook env var (no test-only runtime behavior)
- Added unit tests covering:
  - pause failure => abort before touching device
  - target failure => resume events still emitted (bridge guard path)
  - `--json-timestamps` adds `t_ms` when enabled
  - HalfKay targets => no bridge pause/resume attempted
  - List/doctor target JSON `kind` is stable (`halfkay`)

To do (actionable):
 - Ensure `--json-timestamps` is documented as stable contract (tests cover `t_ms` emission)
 - (Optional) Add a higher-level integration test harness for resume-on-real-IPC-failure without hardware

### Phase 5 (Next): Release Hygiene (No Behavior Surprises)

Goal: ship a clean, reviewable set of commits with no test-only behavior.

To do (actionable):
- Split commits by intent:
  - feat: json timestamps
  - fix: safety abort on bridge pause failure
  - chore/test: regression tests
- Re-run full test matrix locally where possible (at least `cargo test` on Windows)
- Update memory docs only with links to this tracking file (avoid duplicating long plans)

### Phase 6 (Later): Performance Tuning (After Safety Locks)

Goal: reduce total flash time without increasing retries.

Candidates (actionable experiments, one at a time):
- Reduce reboot-to-halfkay latency (safer polling/backoff)
- Investigate early write stall (large jump in `t_ms` around early blocks) and adjust conservative timeouts
- Keep hard rule: retries must stay at 0 in normal conditions

### Phase 7 (Future): Installer Integration

Goal: installer-friendly integration via JSON-only stdout, deterministic exit codes.

To do:
- Finalize event schema + versioning policy
- Provide a reference parser and sample logs

## Change Log (plans and progress)

### 2026-01-29 -> 2026-01-30

- Implemented and validated oc-bridge control-plane integration (pause/resume).
- Fixed Windows measurement capture (PowerShell UTF-16 redirection issue) and added `--json-timestamps`.
- Measured Windows performance and identified bridge stop/start as the biggest avoidable cost; fixed by updating oc-bridge.
- Added safety behavior: if pause fails for serial targets, abort before touching the device.
- Validated unplug/replug mid-flash resumes bridge correctly.

### 2026-01-30 (later)

- Refactored `operation_runner` to inject bridge pause dependency (testable without oc-bridge).
- Removed test-only env hook and replaced with unit tests.

## Worktree Notes (local changes)

Loader changes touched recently (uncommitted at time of writing):
- `midi-studio/loader/src/bin/midi-studio-loader/cli.rs` (adds `--json-timestamps`)
- `midi-studio/loader/src/bin/midi-studio-loader/output/mod.rs`
- `midi-studio/loader/src/bin/midi-studio-loader/output/json.rs`
 - `midi-studio/loader/src/operation_runner.rs` (bridge pause injection + safety + tests)
- `midi-studio/loader/src/api.rs` (FlashError: BridgePauseFailed)
- `midi-studio/loader/src/reboot_api.rs` (RebootError: BridgePauseFailed)
- `midi-studio/loader/src/bridge_control/mod.rs` (service not installed => skipped)
