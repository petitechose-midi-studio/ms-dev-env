# Implementation Plan — Sequencer VirtualList Overlays + Authority Fix

Date: 2026-02-14

Goal: migrate Sequencer overlays to a Bitwig-like VirtualList UI (shared ms-ui components) and fix framework scope authority for gestures.

Principles:
- State is global and view-agnostic; handlers mutate state; UI subscribes and renders.
- Hardware surface sync (encoder modes/positions) is driven by state + active view, not by MIDI handlers.
- Input routing must be consistent across press/release/encoder/gestures.

---

## Roadmap (atomic + testable)

### Phase 0 — Framework fix (open-control/framework)

Fix: `LONG_PRESS`, `DOUBLE_TAP`, `COMBO` must respect `AuthorityResolver` like press/release/encoders.

Verification:
- `cd open-control/framework && pio test -e native`

### Phase 1 — Shared UI (midi-studio/ui)

Add ms-ui components for Bitwig-like modal overlays using `VirtualList`:
- `VirtualListOverlay` (LayoutOverlay shell + header + VirtualList)
- `VirtualListSelectorOverlay` (picker list)
- `VirtualListKeyValueOverlay` (key/value rows with stable value alignment)

Verification:
- `uv run ms build core --target native`

### Phase 2 — Core overlay migration (midi-studio/core)

Replace custom dialog overlays (PatternConfig / StepEdit) with ms-ui VirtualList overlays.

Verification:
- `uv run ms build core --target teensy --env dev`
- `uv run ms build core --target native`
- `uv run ms run core` (timeout)

### Phase 3 — Property selector + macro mapping (midi-studio/core)

Implement:
- `PROPERTY SELECTOR` (VirtualList selector overlay)
- mapping: 8 macro encoders edit active property for visible steps
- surface sync: encoder modes/positions update only for active view

Verification:
- `uv run ms build core --target native`
- `uv run ms run core` (timeout)
- manual smoke: select property -> turn macro encoders -> see step values update; change page -> encoders resync; MIDI IN updates macro state without interfering with sequencer surface.

---

## Progress Log

### 2026-02-14

- [x] Phase 0 — Framework fix + tests (authority gating for longPress/doubleTap/combo)
- [x] Phase 1 — ms-ui VirtualList overlays (VirtualListOverlay + selector + key/value)
- [x] Phase 2 — Core overlay migration (PatternConfig/StepEdit -> VirtualListKeyValueOverlay)
- [x] Phase 3 — Property selector + macro mapping (VirtualList selector + macros edit active property)

Notes:
- Windows-only: ms-dev-env now generates Zig-backed `gcc/g++` wrappers for PlatformIO `native` and sets safe default `SCONSFLAGS=-j1`. See `docs/memories/setup-architecture/windows-native-toolchain-zig.md`.
