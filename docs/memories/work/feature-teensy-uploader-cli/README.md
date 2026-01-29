# Feature: Teensy 4.1 Uploader CLI (Rust)

**Status**: started

**Created**: 2026-01-29
**Updated**: 2026-01-29

## Goal

Ship a minimal, robust command-line flasher dedicated to **Teensy 4.1**.

Constraints:

- Open-source Rust (callable programmatically)
- Reliable on Windows/macOS/Linux
- No UI in this phase (installer integration is later)

## Scope (minimal)

- Flash an Intel HEX to a Teensy 4.1 in HalfKay bootloader mode
- Optional: wait for device
- Optional: reboot after programming
- Deterministic exit codes + optional machine-readable output

Non-goals (for now):

- No multi-board support
- No Teensy 4.0/3.x/2.x
- No hard-reboot "rebootor" support
- No soft reboot (device -> bootloader) unless it is trivial and reliable
- No GUI/TUI

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

Options:

- `--wait` : wait for HalfKay to appear
- `--wait-timeout-ms <n>` : max wait time (0 = forever)
- `--no-reboot` : do not boot after programming
- `--retries <n>` : retries per block (default: 3)
- `--json` : emit machine-readable progress/events to stdout
- `--verbose`

Exit codes (stable):

- `0` success
- `10` no device (HalfKay not found)
- `11` invalid hex
- `12` write failed
- `13` verify failed (if we add verify)
- `20` unexpected error

## Roadmap (very specific)

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

### Phase 2 - Verification (optional but recommended)

If HalfKay supports readback/verify for T4.1, implement verify.
If not, add basic sanity verification:

- validate hex fits inside `code_size`
- validate no unexpected address ranges
- optionally hash the outgoing image and record it in JSON output

Deliverables:

- `--verify` flag (or document why verify is not possible)

### Phase 3 - "Smooth" entry to bootloader (still CLI)

Goal: reduce manual reset presses.

Options to evaluate:

- soft reboot via USB serial (cross-platform) when firmware exposes it
- integrate a tiny "reboot endpoint" in MIDI Studio firmware (future)

Deliverables:

- `--enter-bootloader` best-effort
- fallback prompt "press reset now" after timeout

### Phase 4 - Integration hooks (not implemented here)

This is tracked in the distribution/installer roadmap.

- publish uploader binaries as release assets
- add uploader to `manifest.json`
- installer calls uploader with `--json`
