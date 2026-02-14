# Feature: Step Sequencer (UI-first)

**Status:** started
**Project:** midi-studio/core first (standalone), plugin-bitwig later
**Created:** 2026-01-07
**Updated:** 2026-02-14
**Priority:** high

## Current state

- Core has a top-level View Selector overlay on `LEFT_TOP`.
- Core has a `SequencerView` v0 (8-step grid, pagination, focus, playhead + playback service).
- The reusable v0 engine + internal clock live in OpenControl: `open-control/note` (`oc-note`).
- Shared LVGL UI lives in `midi-studio/ui` (`ms-ui`).

## Next goals (v0)

- Implement the planned Sequencer overlays/mappings (`PATTERN CONFIG`, `STEP EDIT`, etc.).
- Remove/replace v0 legacy gestures once overlays are in place (see `hw-sequencer.md`).
- Persistence direction (when added): a single versioned binary blob via `oc::interface::IStorage`.

## Key decisions (locked)

- Shared LVGL UI lives in `midi-studio/ui` (`ms-ui`).
- Sequencer engine lives in `open-control/note` (`oc-note`) from v0; `midi-studio/core` integrates it via thin adapters.
- Do not start with JSON trees for persistence; keep v0 storage simple and versioned.

## Files

- `tech-spec.md` - v0 scoped spec (UI-first / produit minimal)
- `implementation-plan-v0-framework.md` - execution plan (v0 + structure framework)
- `tech-spec-modular.md` - long-term modular direction (planned)
- `ui-header-progress-strip.md` - Sequencer header improvements (implemented: progress strip + division + length)

## See also

- `docs/memories/midi-studio/hw-layout.md`
- `docs/memories/midi-studio/hw-navigation.md`
- `docs/memories/midi-studio/hw-sequencer.md`
- `docs/memories/midi-studio/shared-ui-ms-ui.md`
