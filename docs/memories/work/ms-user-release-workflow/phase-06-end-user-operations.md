# Phase 06: End-user Operations - Bridge, Bitwig Extension, Firmware Flash, Diagnostics

Status: TODO

## Goal

Implement the end-user operations in ms-manager:

- manage oc-bridge (install/start/stop/restart/status)
- deploy Bitwig extension
- download and flash firmware (via midi-studio-loader)
- provide a diagnostics report export

## Operations (minimum viable)

1) Bridge

- Configure and install bridge as a user service on macOS/Linux.
- Windows: install service with dedicated name (requires upstream oc-bridge flags).
- Never touch the default oc-bridge service/unit; always use the MIDI Studio-specific service name.
- Expose in UI:
  - status
  - restart
  - open config folder

2) Bitwig extension

- Install Bitwig extension only when the selected profile includes it (e.g. `install_set.id == bitwig`).
- Copy the `bitwig-extension` asset to the detected Bitwig Extensions dir.
- UI:
  - show detected path
  - “open folder”
  - “reinstall extension”

3) Firmware flash

- Select firmware based on the installed profile:
  - Standalone profile (`install_set.id == default`) uses the standalone firmware asset.
  - A DAW profile (e.g. `bitwig`) uses its matching firmware asset.
  - Firmware assets are installed into `versions/<tag>/firmware/...` so the active version is under `current/firmware/...`.
- Flash via subprocess:
  - `midi-studio-loader flash ... --json --json-timestamps --json-progress percent`
- Safety net: after the subprocess exits (success/fail/user-cancel), ensure oc-bridge is not left paused:
  - run `oc-bridge ctl status`
  - if paused: run `oc-bridge ctl resume` and record the action in logs/diagnostics
- UI:
  - list targets
  - choose target
  - show progress and final `operation_summary`

4) Diagnostics

- Collect:
  - `midi-studio-loader doctor --json`
  - `oc-bridge ctl status`
  - installed tag/channel
  - logs
- Export as zip.

## Exit Criteria

- End-user can install bundle, restart bridge, deploy extension, and flash firmware.
- Diagnostics export is usable for support.

## Tests

Local (fast):
- Unit tests for path detection and command building.

Local (manual smoke):
- Plug device, flash dry-run, then flash real.
- Restart service and confirm loader can pause/resume.
- Start a flash and cancel it; confirm `oc-bridge ctl status` is not left paused.
