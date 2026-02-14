# Sequencer: Hardware Mappings (Mode Sequencer)

Stable mapping reference for the Sequencer mode, independent from the full tech spec.

References:

- IDs source of truth: `midi-studio/core/src/config/InputIDs.hpp`
- Layout summary: `docs/memories/midi-studio/hw-layout.md`
- Navigation conventions: `docs/memories/midi-studio/hw-navigation.md`
- Sequencer v0 spec: `docs/memories/work/feature-ms-sequencer/tech-spec.md`

## Implementation status (as of 2026-02-14)

Implemented in `midi-studio/core`:

- Top-level MODE SELECTOR overlay on `LEFT_TOP`.
- `SequencerView` v0 (8-step grid, pagination, focus, playhead).
- v0 step toggle via `MACRO` buttons and focus navigation via `NAV`.

Planned (this document describes the target mapping):

- `PATTERN CONFIG`, `PROPERTY SELECTOR`, `SEQUENCER SETTINGS`, `STEP EDIT` overlays.
- Macro encoder turns to edit the selected property.
- Copy/Paste, OPT fine-tune, and other secondary gestures.

## Notation

- Buttons:
  - `P` = press
  - `R` = release
  - `LP` = long press
- Encoders:
  - `T` = turn

## Input ownership invariant (important)

- Overlays are managed by `ExclusiveVisibilityStack` + `OverlayManager`.
- When an overlay is visible, its LVGL scope has input authority.
- Dispatch order is: overlay scope > view scope > global scope (scope=0).
- Therefore:
  - An overlay can override a control by binding that control in overlay scope.
  - If the overlay does NOT bind a control, global bindings may still run.

## Overlay UI templates

Selector overlay (list):

```text
┌────────────────────────────────────┐
│  <TITLE>                           │
├────────────────────────────────────┤
│ > Item 1                           │
│   Item 2                           │
│   ...                              │
└────────────────────────────────────┘
```

Key/Value overlay (rows):

```text
┌────────────────────────────────────┐
│  <TITLE>                    <META> │
├────────────────────────────────────┤
│ > Label A                Value A   │
│   Label B                Value B   │
│   ...                              │
└────────────────────────────────────┘
```

## Main view mapping (Sequencer view, no overlay)

| Control | P | R | LP | T |
|---------|---|---|----|---|
| LEFT_TOP | Open MODE SELECTOR (latch) | - | (reserved breadcrumb) | - |
| LEFT_CENTER | - | Open PATTERN CONFIG | Open TRACK CONFIG | - |
| LEFT_BOTTOM | Open PROPERTY SELECTOR (latch) | - | - | - |
| NAV (enc) | - | - | - | Move focus (step) |
| NAV (btn) | - | Toggle focused step (v0 legacy) | Open SEQUENCER SETTINGS | - |
| OPT (enc) | - | - | - | Fine tune last touched (planned) |
| MACRO btn 1-8 | - | Toggle step 1-8 | Open STEP EDIT (step i) | - |
| MACRO enc 1-8 | - | - | - | Adjust current property (planned) |
| BOTTOM_LEFT | - | Page left | Copy step (planned) | - |
| BOTTOM_CENTER | Play/Pause (global) | - | Stop (planned) | - |
| BOTTOM_RIGHT | - | Page right | Paste step (planned) | - |

Notes:

- Decision: `NAV LP` opens SEQUENCER SETTINGS.
- v0 currently uses `NAV R` to toggle focused step; we may remove this once STEP EDIT + property editing are in place.

## Overlay structure

```text
MODE SEQUENCER (main)
  LEFT_TOP P          -> MODE SELECTOR
  LEFT_CENTER R       -> PATTERN CONFIG
  LEFT_CENTER LP      -> TRACK CONFIG
  LEFT_BOTTOM P       -> PROPERTY SELECTOR
  NAV LP              -> SEQUENCER SETTINGS
  MACRO_i LP          -> STEP EDIT (for visible step i)
```

## Overlay mappings (per control)

The tables below define, for each overlay, what every physical control does.

Legend:

- "no-op" means intentionally unused in that overlay.
- When a button is marked "(latch)", the open action is latched and cleaned up by `OverlayManager::registerCleanup()`.

### Overlay: MODE SELECTOR

- UI: Selector overlay (list)
- Purpose: switch top-level view (Macros / Sequencer)
- Open: `LEFT_TOP P` (latch)
- Close+apply: `LEFT_TOP R`

| Control | Action |
|---------|--------|
| LEFT_TOP P/R | P=open (latch), R=close+apply |
| NAV (enc) T | move selection |
| NAV (btn) R | apply selection (stay open) |
| LEFT_CENTER | no-op |
| LEFT_BOTTOM | no-op |
| OPT (enc) | no-op |
| MACRO btn 1-8 | no-op |
| MACRO enc 1-8 | no-op |
| BOTTOM_LEFT | no-op |
| BOTTOM_CENTER | transport (global) |
| BOTTOM_RIGHT | no-op |

### Overlay: PROPERTY SELECTOR

- UI: Selector overlay (list)
- Purpose: choose which step property is controlled by encoders in Sequencer view
- Open: `LEFT_BOTTOM P` (latch)
- Close+apply: `LEFT_BOTTOM R`
- Cancel: `LEFT_TOP R`

| Control | Action |
|---------|--------|
| LEFT_BOTTOM P/R | P=open (latch), R=close+apply |
| LEFT_TOP R | cancel+close |
| NAV (enc) T | move selection |
| NAV (btn) R | apply selection (stay open) |
| MACRO btn 1-8 R | direct select item i (optional) |
| LEFT_CENTER | no-op |
| OPT (enc) | no-op |
| MACRO enc 1-8 | no-op |
| BOTTOM_LEFT | no-op |
| BOTTOM_CENTER | transport (global) |
| BOTTOM_RIGHT | no-op |

### Overlay: PATTERN CONFIG

- UI: Key/Value overlay
- Purpose (v0): edit pattern-level variables
  - `LEN` (pattern length)
  - `DIV` (step division; derived from `stepsPerBeat`)
  - `CH` (MIDI channel)
- Open: `LEFT_CENTER R` (short click)
- Close+apply: `NAV R` (or `NAV P`, decided in implementation)
- Cancel: `LEFT_TOP R`

| Control | Action |
|---------|--------|
| LEFT_CENTER R | open |
| LEFT_TOP R | cancel+close |
| NAV (enc) T | focus row |
| OPT (enc) T | edit focused value |
| NAV (btn) R | close+apply |
| LEFT_BOTTOM | no-op |
| MACRO btn 1-8 | no-op |
| MACRO enc 1-8 | no-op |
| BOTTOM_LEFT | no-op |
| BOTTOM_CENTER | transport (global) |
| BOTTOM_RIGHT | no-op |

### Overlay: TRACK CONFIG (planned)

- UI: Key/Value overlay (or selector with submenus)
- Purpose: edit track-level variables (scale, FX chain, etc.)
- Open: `LEFT_CENTER LP`
- Close+apply: `NAV R`
- Cancel: `LEFT_TOP R`

| Control | Action |
|---------|--------|
| LEFT_CENTER LP | open |
| LEFT_TOP R | cancel+close |
| NAV (enc) T | focus row |
| OPT (enc) T | edit focused value |
| NAV (btn) R | close+apply |
| LEFT_BOTTOM | no-op |
| MACRO btn 1-8 | no-op |
| MACRO enc 1-8 | no-op |
| BOTTOM_LEFT | no-op |
| BOTTOM_CENTER | transport (global) |
| BOTTOM_RIGHT | no-op |

### Overlay: SEQUENCER SETTINGS

- UI: Key/Value overlay
- Purpose: global sequencer settings (v0 may alias pattern config)
- Open: `NAV LP`
- Close+apply: `NAV R`
- Cancel: `LEFT_TOP R`

| Control | Action |
|---------|--------|
| NAV (btn) LP | open |
| LEFT_TOP R | cancel+close |
| NAV (enc) T | focus row |
| OPT (enc) T | edit focused value |
| NAV (btn) R | close+apply |
| LEFT_CENTER | no-op |
| LEFT_BOTTOM | no-op |
| MACRO btn 1-8 | no-op |
| MACRO enc 1-8 | no-op |
| BOTTOM_LEFT | no-op |
| BOTTOM_CENTER | transport (global) |
| BOTTOM_RIGHT | no-op |

### Overlay: STEP EDIT (planned)

- UI: Key/Value overlay (v0), later can become "8 params mapped to 8 encoders"
- Purpose (v0): edit per-step variables
  - `NOTE`, `VEL`, `GATE` (extendable to prob/timing/slide/accent)
- Open: `MACRO_i LP` (the visible step i)
- Close+apply: `NAV R`
- Cancel: `LEFT_TOP R`

| Control | Action |
|---------|--------|
| MACRO btn i LP | open step edit for step i |
| LEFT_TOP R | cancel+close |
| NAV (enc) T | focus row |
| OPT (enc) T | edit focused value |
| NAV (btn) R | close+apply |
| LEFT_CENTER | no-op |
| LEFT_BOTTOM | no-op |
| MACRO btn 1-8 R | optional: toggle quick action for row i |
| MACRO enc 1-8 | no-op (v0) |
| BOTTOM_LEFT | optional: previous step/page |
| BOTTOM_CENTER | transport (global) |
| BOTTOM_RIGHT | optional: next step/page |
