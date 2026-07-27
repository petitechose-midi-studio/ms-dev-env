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

Persistence is currently split by product semantics:

- Teensy Core Settings use one small non-blocking SDIO file:
  `/core-settings.bin`.
- Teensy musical files use `ProductFileService` below `/midi-studio`:
  - current session: `session/current.mspj`;
  - named projects: `projects/<slug>.mspj`;
  - named Step Presets: `library/step-presets/<id>.mssp`.
- The native simulator uses `./core-settings.bin` for controller settings and
  `.runtime/core-product-files/midi-studio/` for the same Project/Session/Step
  Preset filesystem layout. UX runs isolate product files below their capture
  output.
- The WASM simulator keeps Core Settings in memory and does not currently
  provide persistent product files.

The former `/macros.bin`, fixed Macro/Pattern/Set slot stores and Data Manager
are retired. Future preset families must be named files through
`ProductFileService`; they must not restore fixed-slot identity.

## References

- Hardware IDs: `docs/memories/midi-studio/hw-layout.md`
- Navigation patterns: `docs/memories/midi-studio/hw-navigation.md`
- Shared UI architecture: `docs/memories/midi-studio/shared-ui-ms-ui.md`
- Core architecture docs (authoritative for core app patterns): `midi-studio/core/docs/`
