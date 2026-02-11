# MIDI Studio - Overview (Workspace)

This document describes the MIDI Studio project as it exists inside the `ms-dev-env` workspace.

## Repos / directories

- `midi-studio/core` - controller firmware + native/WASM simulators
- `midi-studio/ui` - shared LVGL UI components (`ms-ui`)
- `midi-studio/plugin-bitwig` - Bitwig integration (firmware + simulators + Java extension)
- `midi-studio/hardware` - hardware design files (not required to build software)

The minimal set of repos that `ms sync --repos` manages is pinned in `ms/data/repos.toml`.

## Build outputs (bin/)

`ms` writes build artifacts into `bin/`.

- Core
  - native: `bin/core/native/midi_studio_core(.exe)`
  - wasm: `bin/core/wasm/midi_studio_core.html` (+ `.js`, `.wasm`)
- Bitwig
  - native: `bin/bitwig/native/midi_studio_bitwig(.exe)`
  - wasm: `bin/bitwig/wasm/midi_studio_bitwig.html` (+ `.js`, `.wasm`)
  - extension: `bin/bitwig/*.bwextension`

## Storage (current)

Persistence is currently implemented as follows:

- Teensy (core): SD card file (non-blocking SDIO)
  - `midi-studio/core/main.cpp` uses `oc::hal::teensy::SDCardBackend` with `/macros.bin`
- Native simulator (core): local file
  - `midi-studio/core/sdl/main-native.cpp` uses `oc::impl::FileStorage` with `./macros.bin`
- WASM simulator (core): in-memory only (no persistence yet)
  - `midi-studio/core/sdl/MemoryStorage.hpp` (`desktop::MemoryStorage`)

## References

- Hardware IDs: `docs/memories/midi-studio/hw-layout.md`
- Navigation patterns: `docs/memories/midi-studio/hw-navigation.md`
- Shared UI architecture: `docs/memories/midi-studio/shared-ui-ms-ui.md`
- Core architecture docs (authoritative for core app patterns): `midi-studio/core/docs/`
