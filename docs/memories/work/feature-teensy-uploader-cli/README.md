# Feature: Teensy 4.1 Uploader CLI (Rust)

**Status**: in_progress

**Created**: 2026-01-29
**Updated**: 2026-01-30

## Goal

Ship a minimal, robust command-line flasher dedicated to **Teensy 4.1**.

Constraints:

- Open-source Rust (callable programmatically)
- Reliable on Windows/macOS/Linux
- No UI in this phase (installer integration is later)

Primary UX goal now:

- `flash firmware.hex` "just works" when exactly one target is detected
- If multiple targets exist: require explicit selection (`--device`) or batch (`--all`)
- `--all` flashes every detected Teensy target sequentially

## Scope (minimal)

- Flash an Intel HEX to a Teensy 4.1 in HalfKay bootloader mode
- Optional: wait for device
- Optional: reboot after programming
- Deterministic exit codes + optional machine-readable output

New in-scope items (to reduce end-user friction):

- Multi-device selection (`--device`) and batch flashing (`--all`)
- Auto target detection (HalfKay and/or USB Serial)
- Safe-by-default behavior when multiple devices are present

Also in-scope: oc-bridge coordination to free the USB Serial port during flashing.

Non-goals (for now):

- No Teensy 4.0/3.x/2.x
- No hard-reboot "rebootor" support
- No firmware signature/verification system (belongs to installer/later)
- No GUI/TUI

Note: soft reboot via USB Serial (134 baud) is now considered "trivial and reliable" when the
running firmware exposes USB Serial.

## Key facts from PJRC teensy_loader_cli (reference)

Repo (implementation): https://github.com/petitechose-midi-studio/loader
Workspace clone: `midi-studio/loader`

Current status (2026-01-29):

- MVP implemented (HalfKay flash + `--wait` + `--json` + retries + reboot)
- Unit tests added for Intel HEX parsing + packet encoding (no hardware needed)
- Next: validate on real Teensy 4.1 (repeat flashes, Windows reliability)

Reference repo (local): `E:\tools\teensy_loader_cli`
Reference docs: https://www.pjrc.com/teensy/loader_cli.html

Note:

- PlatformIO `tool-teensy` currently reports `Teensy Loader, Command Line, Version 2.2`.
- The local repo above contains code that prints `Version 2.3`.
- The protocol details we rely on (HalfKay VID/PID, 1024+64 packet format, 0x60000000 mapping) are stable.

### USB IDs (used by teensy_loader_cli v2.3)

- HalfKay bootloader (target): VID:PID = `16C0:0478`
- Rebootor (hard reboot, out-of-scope): `16C0:0477`
- USB Serial device (soft reboot attempt, libusb path): `16C0:0483`

### MIDI Studio firmware USB type (important)

MIDI Studio firmware builds use `USB_MIDI_SERIAL`:

- `midi-studio/core/platformio.ini`
- `midi-studio/plugin-bitwig/platformio.ini`

In Teensy core descriptors (`framework-arduinoteensy/.../cores/teensy4/usb_desc.h`),
`USB_MIDI_SERIAL` uses PID `0x0489`.

This matters because we can reliably enter bootloader via the **USB Serial 134 baud** mechanism.

### Teensy "134 baud" bootloader entry mechanism (ground truth)

In Teensyduino core, setting the CDC line coding baud rate to `134` triggers a delayed call to
`_reboot_Teensyduino_()`.

This is implemented in PlatformIO's Teensy core:

- `framework-arduinoteensy/cores/usb_serial/usb.c` (handles CDC_SET_LINE_CODING + reboot timer)

### Teensy 4.1 memory geometry

From `teensy_loader_cli.c` MCU table:

- MCU name: `TEENSY41`
- `code_size`: `8126464` bytes
- `block_size`: `1024` bytes

Programming loop:

- Always write block 0 (erase)
- Skip unused/blank blocks after block 0

### HalfKay write packet format (block_size=1024)

For each 1024-byte block at address `addr`:

- Packet size: `block_size + 64` = `1088` bytes
- Header (first 64 bytes):
  - byte 0: `addr & 0xFF`
  - byte 1: `(addr >> 8) & 0xFF`
  - byte 2: `(addr >> 16) & 0xFF`
  - bytes 3..63: zeros
- Payload (bytes 64..1087): 1024 bytes of firmware data

Boot command:

- Send a packet of the same size with bytes `[0..2] = 0xFF` and the rest zero.

### Intel HEX parsing (Teensy 4.x important detail)

teensy_loader_cli supports Intel HEX record type 04 (extended linear address).

For Teensy 4.x it applies a critical mapping:

- HEX may contain addresses with FlexSPI offset `0x60000000`
- When `code_size > 1048576` and `block_size >= 1024`, addresses in `[0x60000000, 0x60000000 + code_size)`
  are remapped by subtracting `0x60000000`.

Our Rust uploader must implement the same mapping.

### Reliability pitfall observed

In teensy_loader_cli.c, per-block write timeout becomes very small after a few blocks:

- first blocks: `45.0s`
- then: `0.5s` per block

On Windows this can lead to intermittent `error writing to Teensy` even when HalfKay is detected.

Our Rust tool must be more robust (higher timeouts + retries + reopen strategy).

## Proposed CLI contract (minimal)

Binary name: `midi-studio-loader`

Commands:

- `flash <path.hex>`
- `list`
- `doctor` (diagnostics)

New/expanded:

- `reboot` (best-effort entry to HalfKay)
- `--device <selector>` (select exactly one target)
- `--all` (flash every detected target sequentially)

Selector formats:

- `serial:COM6` / `serial:/dev/ttyACM0`
- `halfkay:<hid-path>`
- `index:<n>` (index in the `list` output order)

Bridge coordination flags:

- `--no-bridge-control`
- `--bridge-control-port 7999` (oc-bridge IPC)
- `--bridge-service-id <id>` (OS service fallback)

Options:

- `--wait` : wait for HalfKay to appear
- `--wait-timeout-ms <n>` : max wait time (0 = forever)
- `--no-reboot` : do not boot after programming
- `--retries <n>` : retries per block (default: 3)
- `--dry-run` : validate selection + HEX without flashing
- `--json` : emit machine-readable progress/events to stdout
- `--verbose`

Exit codes (stable):

- `0` success
- `10` no device (HalfKay not found)
- `11` invalid hex
- `12` write failed
- `13` ambiguous target (multiple possible targets without explicit selection, or ambiguous HalfKay emergence)
- `20` unexpected error

## Target model

We model "targets" as:

- **HalfKay targets**: devices already in bootloader mode (HID `16C0:0478`)
- **Serial targets**: USB Serial ports belonging to PJRC VID `16C0` (usually our app-mode devices)

`--all` includes all targets from the initial snapshot (HalfKay + Serial) and flashes them
sequentially.

## Serial -> correct HalfKay association (no brittle COM<->HID mapping)

When flashing a Serial target:

1) Snapshot `before = set(list_halfkay_paths())`
2) Trigger soft reboot on the serial port (set baud 134)
3) Wait for HalfKay to appear:
   - poll list_halfkay_paths()
   - compute `new = paths - before`
   - if `len(new) == 1` => select that path
   - if `len(new) > 1` => ambiguous (fail safe)
   - if timeout => no device
4) Flash *by that path* (open by path; reopen by path on retries)

This provides correct device targeting even when multiple Teensys are connected.

## oc-bridge pause/resume (high ROI)

Problem: the bridge commonly owns the serial port and prevents a soft reboot / flashing.

Solution: prefer an in-process pause/resume API that releases the serial port without stopping the
whole bridge process.

- oc-bridge exposes local IPC on `127.0.0.1:7999`:
  - `oc-bridge ctl pause` (must ACK only once serial is closed)
  - `oc-bridge ctl resume`
  - `oc-bridge ctl status`

Uploader behavior:

1) Prefer IPC pause/resume
2) Fallback: stop/start OS service (when installed)

## JSON contract (installer-friendly)

JSON lines to stdout with:

- `schema`: integer (start at 1)
- `event`: string
- `target_id`: stable id for selection (e.g. `serial:COM6`, `halfkay:<path>`)
- `kind`: `serial|halfkay`

Key events:

- `discover_start`, `discover_done`, `target_detected`, `target_selected`, `target_ambiguous`
- `soft_reboot`, `soft_reboot_skipped`, `halfkay_appeared`
- existing flash events: `hex_loaded`, `block`, `retry`, `boot`, `done`
- per-target summary for `--all`: `target_done` with `ok=true/false` + `error_code`

## Roadmap (very specific)

### Hardening backlog (perf / footprint / UX)

These items are not required for the MVP flasher to work, but they are high ROI before installer
integration.

#### P0

- [x] Perf/footprint: reduce sysinfo refresh scope in process fallback
  - Avoid `System::new_all()` and full refresh; refresh only processes with exe/cmd when needed.
- [x] Perf: avoid per-block heap allocations while building HalfKay reports
  - Reuse a fixed-size report buffer (stack or caller-provided) instead of allocating a `Vec`.
- [x] UX: `doctor` command
  - Show detected targets, oc-bridge IPC reachability/status, service status, and key hints.
- [x] UX: `flash --dry-run`
  - Validate `.hex`, compute blocks-to-write, resolve target selection, but do not pause/reboot/flash.

#### P1

- [x] UX: default progress output (human-friendly) while keeping `--json` stable
  - Show phases + block progress + percent to stderr.
- [ ] UX: make bridge control policy explicit
  - Add `--bridge-method=auto|control|service|process|none` (or `--no-process-fallback`).
- [x] UX: make ambiguous target errors more actionable
  - When exiting `13`, print `list` output and exact `--device` examples.
- [x] Docs: expand `midi-studio/loader/README.md` for doctor/dry-run and troubleshooting.

#### P2

- Footprint: reduce firmware image memory
  - [x] Remove redundant HEX "mask" tracking where safe.
  - [ ] Optional: allocate only up to the highest address used (rounded to block size).
  - [ ] Optional: sparse-per-block representation if we want to go below ~8MB.

- Perf: reduce device discovery overhead in `--wait` loops
  - [ ] Cache HID/serial snapshots for a short interval during polling.
  - [ ] Avoid recreating HID contexts unnecessarily.

- Build/footprint: optional dependencies
  - [x] Feature-gate process fallback (sysinfo) for pure-library consumers.

### Architecture hardening (SOLID / maintainability)

#### P0

- [x] CLI: split responsibilities (commands/output) and centralize output rendering
  - Event-driven reporter (`Reporter` + typed `Event`) for consistent JSON/human output.
- [x] Lib: modularize `bridge_control`
  - Split into `ipc`, `service`, `process`, `cmd` submodules.
- [x] Lib: move reboot flow into a library use-case
  - `reboot_api` reuses the same event stream as flashing.

- [ ] Lib: rename flash-scoped event type to an operation-scoped event type
  - Replace `FlashEvent` with `OperationEvent` (no legacy support; allowed since there are no external users).
  - Keep JSON event names stable (contract), but the Rust type should reflect the multi-operation scope.
- [ ] Lib: introduce an operation runner shared by flash/reboot
  - Shared pipeline: discover -> select -> bridge pause/resume -> per-target run -> aggregation.
  - Flash/reboot only implement the per-target action.
- [ ] Tests: strengthen JSON contract coverage
  - Table-driven tests covering every operation event variant -> expected JSON fields.
  - Add tests for `doctor`, `list`, and `dry_run` JSON payloads.

#### P1

- [ ] Lib: typed selection API (avoid re-parsing selector strings)
  - Add a parsed selector type exposed by the lib.
- [ ] Bridge: explicit policy surface
  - `--bridge-method=auto|control|service|process|none` + optional `--no-process-fallback`.
- [ ] IPC: formal request/response schema
  - Add `schema` fields and strict parsing for oc-bridge control plane.

### Phase 0 - Repo + build system

Deliverables (done):

- New repo `petitechose-midi-studio/loader` (Rust workspace)
- CI workflow running fmt/clippy/test/build on Windows/macOS/Linux
- License set to `MIT OR Apache-2.0`

### Phase 1 - Minimal flashing in HalfKay mode

Goal: user presses Program/Reset to enter HalfKay; tool flashes reliably.

Tasks:

1) Device discovery
   - enumerate HID devices, select VID:PID `16C0:0478`
   - handle "multiple devices" deterministically (pick first; later add selector)

2) Intel HEX loader (Teensy 4.1)
   - parse records 00/01/04
   - apply FlexSPI address mapping (subtract `0x60000000`)
   - build an in-memory image model for `[0, code_size)` (sparse representation preferred)
   - compute which 1024-byte blocks are non-blank

3) Packet encoder
   - build the 1088-byte packet format (3-byte addr + 61 zeros + 1024 data)
   - boot packet (0xFF 0xFF 0xFF)

4) Write loop
   - always write block 0
   - write only blocks that contain any non-0xFF bytes
   - per-block retry loop
   - on failure: close and reopen device, re-try the same block
   - conservative timing:
     - block 0 timeout higher (erase)
     - all other blocks >= a few seconds (not 0.5s)

5) UX
   - clear text output + optional `--json` progress
   - error messages include actionable hints (press reset, close competing apps)

Acceptance criteria:

- 20 consecutive flashes on Windows without a single `write failed`
- 10 consecutive flashes on macOS + Linux
- Works with `midi-studio/*` firmware HEX produced by PlatformIO

### Phase 2 - Multi-target selection + auto detection (next)

Goal: reduce friction and make the uploader safe in multi-device setups.

Tasks:

1) Implement target discovery (HalfKay + Serial)
2) Add `--device` and `--all` to the CLI
3) Auto-selection:
   - if exactly one HalfKay exists, select it (even if other serial targets exist)
   - else if exactly one total target exists, select it
   - else ambiguous without explicit selection
4) Implement Serial->HalfKay association via "delta HalfKay" approach
5) Add stable exit code for ambiguous target
6) Expand JSON events for discovery and per-target summaries
7) Add unit tests for selector parsing, resolve, and delta logic

Acceptance criteria:

- App-mode only (USB Serial): `flash fw.hex` enters HalfKay and flashes without specifying COM
- Bootloader only (HalfKay): `flash fw.hex` flashes without `--wait`
- Multiple devices: without selector exits ambiguous + prints selectable ids
- `--device` flashes the chosen device; `--all` flashes all targets sequentially

### Phase 3 - Verification (optional but recommended)

If HalfKay supports readback/verify for T4.1, implement verify.
If not, add basic sanity verification:

- validate hex fits inside `code_size`
- validate no unexpected address ranges
- optionally hash the outgoing image and record it in JSON output

Deliverables:

- `--verify` flag (or document why verify is not possible)

### Phase 4 - "Smooth" UI (later)

Goal: reduce manual reset presses.

Options to evaluate:

- soft reboot via USB serial (cross-platform) when firmware exposes it
- integrate a tiny "reboot endpoint" in MIDI Studio firmware (future)

Deliverables (later):

- progress bar / interactive command (no args)
- installer integration

### Phase 4 - Integration hooks (not implemented here)

This is tracked in the distribution/installer roadmap.

- publish uploader binaries as release assets
- add uploader to `manifest.json`
- installer calls uploader with `--json`
