# Tracking: oc-bridge User Daemon Only

Last updated: 2026-02-05

## Goal

Make `oc-bridge` run as a per-user background daemon on all desktop platforms.

Constraints:

- Background task must have exactly one supported mode: user daemon.
- No system-wide Windows Service / systemd system units.
- No collisions: single daemon instance; TUI must not fight daemon for ports/serial.
- Uniform UX across Windows/macOS/Linux.
- Workflow must be simpler and more reliable for:
  - Bitwig host (expects UDP :9000)
  - firmware flashing (uses `oc-bridge ctl pause/resume/status` on 127.0.0.1:7999)

## Current State (snapshot)

- Daemon mode is per-user: `oc-bridge --daemon` (single instance lock) + auto-reconnect serial.
- Control plane: TCP `127.0.0.1:7999` JSON `{schema:1, cmd:...}`; supports pause/resume/status/shutdown.
- Log broadcast: UDP `127.0.0.1:9999` (daemon -> TUI receiver).
- Autostart is owned by `ms-manager` (tray/background). It supervises `oc-bridge --daemon`.

Note (product direction): end-user releases should not expose any oc-bridge lifecycle management.
`oc-bridge` stays a dumb dataplane daemon (plus dev TUI/CLI); `ms-manager` owns autostart/supervision.
- Config + device presets live in per-user config dir (migrates once from legacy next-to-exe).

## Target Architecture

- One daemon process per user session:
  - opens Serial
  - binds Host UDP port (9000/9001/9002)
  - runs control plane (7999)
  - broadcasts logs (9999)
- One or more clients (TUI/CLI) attach:
  - read logs (UDP receiver)
  - control daemon (TCP control plane)
  - edit config file (open in editor)
  - restart/reload daemon

## Design Decisions

### 1) Config location (standard per-user)

Move config + presets to per-user config dirs (not next to the exe).

- Windows: %APPDATA%\\OpenControl\\oc-bridge\\config.toml
- macOS:   ~/Library/Application Support/OpenControl/oc-bridge/config.toml
- Linux:   $XDG_CONFIG_HOME/opencontrol/oc-bridge/config.toml (fallback ~/.config/...)

Migration (one-shot): if legacy config exists next to the exe and the new config does not exist, copy it.

### 2) Single instance guarantee

Daemon takes an exclusive lock in the config dir (e.g. `oc-bridge.lock`).

- Second daemon instance exits fast with a clear message.
- Control port bind (7999) is a second line of defense.

### 3) Autostart (per-user)

Autostart is handled by `ms-manager` (per-user) on all platforms.

oc-bridge does not install/remove OS autostart entries; it only runs `--daemon` and exposes `ctl`.

### 4) Control plane extensions

Keep `pause/resume/status` stable for midi-studio-loader.

Add:

- `ping` / `info` (pid, version, config path, ports)
- `reload` (re-read config; may return restart_required)
- `restart` / `shutdown` (clean exit so supervisor restarts)

Daemon mode must fail fast if control plane cannot bind.

### 5) TUI becomes a daemon client

- If daemon is running: attach (logs + ctl).
- If daemon is not running: offer start + autostart install.
- Remove legacy "run local bridge" / "monitor service" logic.

## Work Plan (checklist)

### Phase 1: Config + Lock

- [x] Implement per-user config dir resolution + migration from legacy next-to-exe.
- [x] Move device presets under per-user config dir.
- [x] Add daemon lock file (exclusive).

### Phase 2: Control plane

- [x] Extend IPC schema (request schema + new commands).
- [x] Make `--daemon` fatal if control plane bind fails.
- [x] Add `shutdown` support.
- [ ] Add `restart`/`reload` support.

### Phase 3: Autostart

- [x] Remove Windows Service legacy code + dependencies.
- [x] Remove oc-bridge autostart management (moved to ms-manager).
- [x] ms-manager supervises oc-bridge daemon and cleans legacy oc-bridge autostarts.

### Phase 4: TUI Attach + No Collisions

- [x] TUI detects daemon via control plane.
- [x] TUI attaches to log broadcast receiver.
- [x] TUI actions: pause/resume, restart, open config, autostart install/uninstall.
- [x] Ensure log receiver bind conflicts handled gracefully (multi-client).

### Phase 5: Integration Follow-ups

- [ ] Update ms-manager: stop calling `oc-bridge install/uninstall` (service); use `ctl` and/or autostart.
- [ ] (Optional) Update midi-studio-loader default bridge method to control-only.

## Progress Log

### 2026-02-04

- Implemented (WIP, compiling on Windows):
  - Per-user config dir + one-shot migration from legacy next-to-exe.
  - Embedded defaults (`config/default.toml` and `config/devices/teensy.toml`) so a clean install can self-bootstrap.
  - Daemon single-instance lock (`oc-bridge.lock`).
  - Control plane: bind is now fail-fast (pre-bind listener) + added `shutdown` command.
  - New autostart module (per-user):
    - Windows: Task Scheduler (basic ONLOGON task)
    - Linux: systemd user unit
    - macOS: LaunchAgent
  - CLI surface migrated to `oc-bridge autostart ...` (service subcommands being removed).
  - TUI refactor in progress: remove local/service bridge execution; act as daemon client (ctl + logs).

### 2026-02-05

- Fixed TUI startup when UDP log receiver port is already bound (multi-client): logs become optional; UI shows LOG unavailable and TUI continues running.
- Windows autostart: switched from Task Scheduler to HKCU Run key to avoid permission errors in locked-down environments; `autostart install/start/stop/uninstall` and TUI start/stop now work without admin.
- Fixed daemon restart race: wait for instance lock release before re-starting (prevents intermittent "InstanceLock" failures and leaving the daemon stopped after restart).
- Windows daemon UX: hide intrusive console window when launched at login; autostart writes `--daemon --no-console` to avoid a visible terminal.
