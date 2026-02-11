# Sequencer Overlay Mappings

This file is the stable place to keep sequencer mappings independent from the full tech spec.

Current status:

- Sequencer engine is still planned (no playback/MIDI engine yet).
- Core has UI scaffolding:
  - a top-level View Selector overlay on `LEFT_TOP`
  - a placeholder `SequencerView` (8-step grid)
- The canonical spec is `docs/memories/work/feature-ms-sequencer/tech-spec.md`.

## Main view mapping (draft)

| Control | Press | Long press | Turn |
|---------|-------|------------|------|
| LEFT_TOP | Mode selector | Breadcrumb | - |
| LEFT_CENTER | Pattern config | Track config | - |
| LEFT_BOTTOM | Property selector | - | - |
| NAV | Sequencer settings | - | Select track (1-16) |
| OPT | - | - | Fine tune last touched |
| MACRO 1-8 | Toggle step | Step edit + MIDI learn | Adjust property |
| BOTTOM_LEFT | Page left | Copy step | - |
| BOTTOM_CENTER | Play/Pause | Stop | - |
| BOTTOM_RIGHT | Page right | Paste step | - |

## Overlay structure (draft)

```
MODE SEQUENCER (main)
  LEFT_TOP press      -> MODE SELECTOR
  LEFT_CENTER press   -> PATTERN CONFIG
  LEFT_CENTER long    -> TRACK CONFIG
  LEFT_BOTTOM press   -> PROPERTY SELECTOR
  NAV press           -> SEQUENCER SETTINGS
  MACRO long          -> STEP EDIT
```

For details (all overlays, parameters, behavior), see:

- `docs/memories/work/feature-ms-sequencer/tech-spec.md`
