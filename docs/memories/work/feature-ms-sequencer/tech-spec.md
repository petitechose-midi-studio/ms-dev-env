---
title: 'Step Sequencer (UI-first)'
slug: 'step-sequencer'
created: '2026-01-07'
updated: '2026-02-12'
status: 'started'
---

# Tech-Spec: Step Sequencer (UI-first)

This is the current, scoped plan.

For long-term direction:

- Modular spec (v1+ planned): `docs/memories/work/feature-ms-sequencer/tech-spec-modular.md`
- Execution plan (v0 + framework structure): `docs/memories/work/feature-ms-sequencer/implementation-plan-v0-framework.md`

## Current baseline (already implemented)

- Core: top-level View Selector overlay on `LEFT_TOP` (shared selector UI).
- Core: `SequencerView` UI-first:
  - 8 steps visible with pagination, focus, and playhead state.
  - toggle steps via `MACRO_1..MACRO_8`.
  - navigate focus via `NAV` (turn) and toggle focused step via `NAV` (press).
- Shared UI library: `midi-studio/ui` (`ms-ui`).

## Scope v0 (next)

Goal: a UI-first POC that is easy to iterate on.

In scope:

- Tiny playback stub (internal clock + USB MIDI out):
  - fixed default resolution: 1/16
  - fixed default channel: 1
  - gate% schedules note-off (gate=0 mutes)
  - engine runs regardless of active view (Macro/Sequencer/overlays)
- Keep v0 state minimal and settings-ready (no magic numbers).

Out of scope (v0):

- Full multi-track (16 tracks), FX chain, Bitwig sync, file browser, protocol FILE_*.
- JSON-based persistence trees.

## Architecture decisions (locked)

- Engine placement (v0): implement a reusable core in `open-control/note` ("oc-note"), integrate into `midi-studio/core` with thin adapters.
- Persistence: out of scope for v0 (decide format when engine stabilizes).
- Shared LVGL components: v0 UI stays in `midi-studio/ui` (`ms-ui`). A generic sequencer widget can move later if reused.

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
