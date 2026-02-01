# Phase 03: oc-bridge Upstream - Service Name Config + Linux Desktop Toggle

Status: DONE

## Goal

Upstream changes to `open-control/bridge` so MIDI Studio can install and manage oc-bridge
without colliding with other oc-bridge users.

## Required Changes

1) Windows service name configurability

- Implemented CLI flags:
  - `oc-bridge install [--service-name <name>] [--service-exec <absolute_path>] [--no-desktop-file]`
  - `oc-bridge uninstall [--service-name <name>]`
  - `oc-bridge ctl ...` unchanged (control plane is independent).

Constraints:
- Backwards compatible defaults:
  - If flags not passed, keep current behavior for existing users.
- Never delete/overwrite services not named by the user.

Additional requirement (critical for upgrade safety):
- Allow overriding the service executable path used in the service definition.
  Rationale: `current_exe()` may resolve to a versioned path even when executed via `current/`.
  MIDI Studio needs the service ExecStart/BinaryPath to reference a stable `current/` path.

Recommended flag:
- `--service-exec <absolute_path>`

2) Linux systemd user unit name configurability

- Add `--service-name <name>` support for Linux service unit.
- Ensure the generated unit file uses the correct name.

Additional requirement (critical for upgrades):
- Allow overriding ExecStart path to the stable `current/` path.
  Recommended flag: `--service-exec <absolute_path>`.

3) Linux: disable .desktop install

- Add flag: `oc-bridge install --no-desktop-file`.
- MIDI Studio will manage its own desktop integration; oc-bridge should not add extra menu entries.

## MIDI Studio Default Names

Recommended values (documented in ms-manager):
- Windows service name: `MidiStudioBridge`
- Linux user unit: `midi-studio-bridge`
- macOS LaunchAgent id: `com.petitechose.midi-studio.bridge`

## Exit Criteria

- oc-bridge supports configurable service name on Windows and Linux.
- oc-bridge supports `--service-exec <absolute_path>` on Windows and Linux, and the installed service/unit uses it.
- Linux `--no-desktop-file` works.
- Existing oc-bridge users are not broken (defaults unchanged).

## Implementation Notes

- Upstream PR: `https://github.com/open-control/bridge/pull/2` (merged)
- Default behavior preserved:
  - Windows default service name remains `OpenControlBridge`
  - Linux default unit name remains `open-control-bridge`
  - If `--service-exec` is not provided, oc-bridge keeps using `current_exe()`.
- Validation:
  - `--service-name` allows only ASCII alnum + `- _ .` and max length 128.
  - Linux additionally rejects names ending with `.service`.
  - `--service-exec` must be an absolute path to an existing file.
- Linux desktop integration:
  - `.desktop` install is skipped when `--no-desktop-file` is provided.
- Not implemented (intentional): `--service-display-name` / `--service-description`.
  - Rationale: keep the surface area minimal until a real use-case appears.
- macOS: service management is not supported; commands return `PlatformNotSupported`.

## Tests

Local:
- `cargo test` in `open-control/bridge`

CI:
- `cargo fmt`
- `cargo clippy --all-targets -- -D warnings`
- `cargo test` (Windows/Linux/macOS)

Windows (manual smoke):
- `oc-bridge install --service-name MidiStudioBridge`
- verify service exists and starts
- `oc-bridge uninstall --service-name MidiStudioBridge`

Windows (manual smoke - exec override):
- `oc-bridge install --service-name MidiStudioBridge --service-exec <ABSOLUTE_PATH_TO_CURRENT_OC_BRIDGE_EXE>`
- verify the service points to the provided path
- `oc-bridge uninstall --service-name MidiStudioBridge`

Linux (manual smoke):
- `oc-bridge install --service-name midi-studio-bridge --service-exec <ABSOLUTE_PATH_TO_CURRENT_OC_BRIDGE> --no-desktop-file`
- `systemctl --user status midi-studio-bridge`
- verify the unit ExecStart uses the provided path
- ensure no `.desktop` is created
