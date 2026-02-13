---
title: 'Sequencer Header UI: Progress Strip + Division + Length'
slug: 'sequencer-header-progress-strip'
created: '2026-02-13'
updated: '2026-02-13'
status: 'review'
---

# Sequencer Header UI: Progress Strip + Division + Length

## Progress

- 2026-02-13: Implemented `SequencerHeaderBar` (SEQ + division + LEN + 8-segment progress strip) and refactored `SequencerView` to use it.

## Problem

In `midi-studio/core`, `SequencerView` currently uses the same `TopBar` component as `MacroView`.

`TopBar` is bound to `core::state::StatusBarState::pageName`, which represents the **Macro page name** ("Page 1", ...).

In Sequencer mode, showing "Page 1" in the top bar is misleading and reduces readability.

## Goal

Make the Sequencer view header self-explanatory and playback-friendly:

- Replace the Macro page title with a Sequencer title (ex: `SEQ`).
- Show rhythmic division (value of a step) on the right (ex: `1/16`).
- Show pattern length on the right (ex: `LEN 18`).
- Add a thin progress strip directly under the top bar:
  - 8 mini-bars (2-3 px tall), each representing a page of 8 steps.
  - A playhead marker that moves with playback.
  - Marker disappears when playback stops (`playheadStep == -1`).
  - Pages beyond `length` are visually disabled.
  - Viewed page is visually highlighted (no auto-follow contract).

## UI Wireframe (ASCII)

Example: `length=18`, `stepsPerBeat=4` => `1/16`.

Legend:

- `#` completed (before playhead)
- `=` valid but not completed
- `-` out of pattern (past `length`)
- `|` playhead marker
- `{ ... }` currently viewed page

```text
SEQ                                              1/16   LEN 18
{########}[##|=====][==------][--------][--------][--------][--------][--------]
```

## Implementation Strategy (clean + consistent)

Adopt the same patterns used in `midi-studio/plugin-bitwig`:

- Stateless header widget with `render(props)` (cf. `ui/device/DeviceStateBar.*`).
- Layout via LVGL flex (top row: left title / right info; strip row under it).
- SequencerView remains the orchestrator: it reads state and renders widgets.
- Drive updates via `oc::state::SignalWatcher` + a 60Hz one-shot `lv_timer`.

Framework / libs that help:

- `oc::state::SignalWatcher`: coalesced updates from multiple signals.
- `lv_timer` (LVGL): cap render rate (~60Hz) and coalesce bursts.
- `oc::ui::lvgl::style::StyleBuilder`: consistent styling.

## File Plan (core)

Create:

- `midi-studio/core/src/ui/sequencer/SequencerHeaderBar.hpp`
- `midi-studio/core/src/ui/sequencer/SequencerHeaderBar.cpp`

Role:

- Provide a dedicated header for SequencerView.
- Implement `render(Props)` for:
  - left title ("SEQ")
  - right info (`division`, `LEN`)
  - progress strip (8 mini-bars + marker)

Modify:

- `midi-studio/core/src/ui/view/SequencerView.hpp`
- `midi-studio/core/src/ui/view/SequencerView.cpp`

Role:

- Replace `TopBar` usage with `SequencerHeaderBar`.
- Move current page bar logic out of the body and into the header progress strip.
- Extend watched signals to include `stepsPerBeat` (for division display).

No deletions expected.

## Notes

- This work is UI-only and does not change the v0 engine behavior.
- If later we want smoother-than-step progress, we can add an optional UI signal for tick/phase, but it is not required for the current spec.
