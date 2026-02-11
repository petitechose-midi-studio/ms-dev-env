---
title: 'Step Sequencer (UI-first)'
slug: 'step-sequencer'
created: '2026-01-07'
updated: '2026-02-11'
status: 'started'
---

# Tech-Spec: Step Sequencer (UI-first)

This is the current, scoped plan.

## Current baseline (already implemented)

- Core: top-level View Selector overlay on `LEFT_TOP` (shared selector UI).
- Core: placeholder `SequencerView` (8-step grid) so switching views is visible.
- Shared UI library: `midi-studio/ui` (`ms-ui`).

## Scope v0 (next)

Goal: a UI-first POC that is easy to iterate on.

In scope:

- Minimal reactive sequencer state (standalone):
  - 8 or 16 steps
  - enabled flag per step
  - optional per-step note/velocity in v0 (can be UI-only initially)
- Input mapping for basic editing:
  - toggle a step
  - move the focused step
- Optional later: tiny playback stub (internal clock + USB MIDI out) once UI is stable.

Out of scope (v0):

- Full multi-track (16 tracks), FX chain, Bitwig sync, file browser, protocol FILE_*.
- JSON-based persistence trees.

## Architecture decisions (locked)

- Engine placement (v0): implement inside `midi-studio/core` first (internal module). Extract to OpenControl only when stable and reused.
- Persistence (v0+): single versioned binary blob via `oc::interface::IStorage`.
- Shared LVGL components belong in `midi-studio/ui` (`ms-ui`), not OpenControl.

## UX contract (baseline)

- `LEFT_TOP` opens the View Selector overlay.
- `NAV` encoder selects an item.
- `NAV` press confirms.
- `LEFT_TOP` release confirms + closes.

## References

- Hardware IDs: `docs/memories/midi-studio/hw-layout.md`
- Navigation patterns: `docs/memories/midi-studio/hw-navigation.md`
- Sequencer mappings (draft): `docs/memories/midi-studio/hw-sequencer.md`
- Shared UI (`ms-ui`): `docs/memories/midi-studio/shared-ui-ms-ui.md`
