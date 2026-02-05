# ms-manager Bridge Supervision

Last updated: 2026-02-05

Goal
- End-user: controllers work by default for the full user session with zero manual actions.
- Only one process autostarts at login: `ms-manager` (tray/background).
- `ms-manager` supervises `oc-bridge --daemon` (spawn, health checks, cleanup legacy, restart on crash).
- `oc-bridge` stays "dumb" and testable (TUI/CLI for dev + dataplane daemon).

Non-goals
- Perfect availability across OS reboots and app crashes (best-effort is OK).
- System-wide services or admin-only installation.

Responsibilities

oc-bridge (open-control/bridge)
- Dataplane bridge: controller <-> host transports (Serial/UDP/WebSocket) + auto-reconnect for Serial.
- Local control plane (TCP 127.0.0.1): pause/resume/status/ping/info/shutdown.
- Logs (firmware + system) + optional live monitoring.
- No OS autostart/service install/uninstall in end-user flow.

ms-manager (petitechose-midi-studio/ms-manager)
- Sole per-user autostart at login; runs in tray/background.
- Spawns and supervises `oc-bridge --daemon` for the session.
- Exposes bridge status/info/logs in UI.
- Performs legacy cleanup (disable/remove old oc-bridge autostarts) and documents migration.

Decisions (current)

Lifecycle
- On explicit Quit in ms-manager: stop oc-bridge cleanly (`ctl shutdown`).
- On ms-manager crash/kill: oc-bridge may continue running; this is acceptable.
- On ms-manager relaunch: detect existing oc-bridge daemon and reconnect; if unhealthy/unreachable, kill and restart cleanly.

Logs
- Source of truth: file logs with rotation (multi-client safe, no port collision).
- Size is bounded and configurable.
- Optional live stream remains for dev tooling (TUI).

Ports
- MIDI Studio defaults to `127.0.0.1:7999` control plane, but oc-bridge remains configurable.
- MIDI Studio may override via its own config and/or CLI args when spawning oc-bridge.

Legacy Cleanup
- Remove/disable all legacy oc-bridge autostarts (Run key / Task Scheduler / LaunchAgent / systemd user unit / wrapper scripts).
- No "install/uninstall" terminology in oc-bridge; only ms-manager owns product installation.

Implementation Plan

1) oc-bridge: file logs + rotation
- Write to per-user config dir (next to config.toml) as `bridge.log`.
- Rotation: `bridge.log` -> `bridge.log.1..N` when `max_bytes` exceeded.
- Configurable: enable/disable, max_bytes, max_files, flush interval, and what log kinds to persist.
- Performance: non-blocking bridge; bounded queue; drop strategy for high-volume logs.

2) ms-manager: supervision + reconciliation
- Health check by control plane `ping`.
- Reconnect if daemon already running.
- If ping fails but daemon seems present: attempt shutdown; if still unhealthy, kill and respawn.
- Kill must be targeted (by pid or executable path + `--daemon`), never blanket kill by name.

3) Legacy cleanup (strict)
- Windows:
  - remove HKCU Run values matching OpenControlBridge* and any value launching oc-bridge.
  - disable/delete scheduled task `\\OpenControlBridge` if present.
  - remove legacy wrapper `start-bridge.bat` if found.
- macOS: unload + remove legacy LaunchAgent plist.
- Linux: stop/disable + remove systemd user unit.
- Document remaining cases requiring admin rights.

4) oc-bridge TUI clarity
- No abbreviations: "Controller", "WebSocket", "Control port", "Logs port", "Protocol".
- Remove ambiguous naming (`B` serial release vs `P` logs freeze) by explicit labels.
- Ensure the TUI never implies it manages daemon lifecycle.

5) Documentation
- Update oc-bridge README to match reality:
  - config location (per-user), no Windows Service, no install/uninstall.
  - daemon + control plane commands.
  - TUI keys (current).
  - recommended end-user flow via ms-manager.
- Add migration/cleanup notes.

6) CI
- Ensure tests/format/clippy pass on Windows/macOS/Linux for both repos.

Open Questions
- Logs live streaming: keep UDP 9999 dev-only, or replace with multi-client stream later.
- Port override contract: add explicit daemon CLI overrides for control/log ports vs relying on config.
- Whether oc-bridge should publish a small runtime info file (pid/ports/log path) for easier reconciliation.

Progress Log

### 2026-02-05

- oc-bridge: added rotating file logs (configurable size/retention/filters) and updated default config.
- oc-bridge TUI: clarified labels (no "Ctrl" abbreviations; Serial Release/Attach vs Logs Freeze/Follow).
- ms-manager: added a bridge supervisor reconciliation step (targeted kill by payload exe; fallback strict kill for legacy daemons).
- ms-manager: added "Open" action for bridge logs in Dashboard (opens bridge log file/folder).
- ms-manager: tray Quit now attempts a clean daemon shutdown then enforces no oc-bridge daemon remains.
