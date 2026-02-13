# Feature: Step Sequencer (UI-first)

**Status:** started
**Project:** midi-studio/core first (standalone), plugin-bitwig later
**Created:** 2026-01-07
**Updated:** 2026-02-13
**Priority:** high

## Current state

- Core has a top-level View Selector overlay on `LEFT_TOP`.
- Core has a `SequencerView` v0 (8-step grid, pagination, focus, playhead + playback service).

## Immediate goals (v0)

- Standalone UI POC first (no engine required initially): step grid + step toggle + basic navigation.
- Minimal reactive state for sequencing (separate from Macro state).
- Persistence direction (when added): a single versioned binary blob via `oc::interface::IStorage`.

## Key decisions (locked)

- Shared LVGL UI lives in `midi-studio/ui` (`ms-ui`).
- Sequencer engine first version lives inside `midi-studio/core` (internal module) until stable.
- Do not start with JSON trees for persistence; keep v0 storage simple and versioned.

## Files

- `tech-spec.md` - v0 scoped spec (UI-first / produit minimal)
- `implementation-plan-v0-framework.md` - execution plan (v0 + structure framework)
- `tech-spec-modular.md` - long-term modular direction (planned)
- `ui-header-progress-strip.md` - planned Sequencer header improvements (readability + playhead strip)

## See also

- `docs/memories/midi-studio/hw-layout.md`
- `docs/memories/midi-studio/hw-navigation.md`
- `docs/memories/midi-studio/hw-sequencer.md`
- `docs/memories/midi-studio/shared-ui-ms-ui.md`
