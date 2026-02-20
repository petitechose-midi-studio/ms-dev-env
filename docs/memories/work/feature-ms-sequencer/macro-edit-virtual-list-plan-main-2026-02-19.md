# Implementation Plan - Macro Edit VirtualList v2 (main)

Date: 2026-02-19
Status: Active

## Goal

Align Macro view editing with the same VirtualList architecture used elsewhere,
with a clear and testable interaction model:

- main overlay = property selector (CH / CC)
- optional value selector = precise value editing
- fast live edit via OPT
- long-press open + release-window behavior (latch vs hold-commit)
- page and macro quick switching while overlay is open

Framework dependency is now explicit:

- `docs/memories/work/feature-ms-sequencer/framework-input-release-routing-plan-main-2026-02-19.md`

MacroEdit implementation and stabilization continue in parallel with this framework plan.

---

## Final UX Contract (locked)

### Open

- `MACRO_i` long press (`500ms`) opens `MacroEdit` for macro `i`.
- This first overlay is the property selector (rows: `Channel`, `CC`).

### Release policy right after open

- quick release after open (`< 300ms`) => overlay stays open (latch behavior)
- late release after open (`>= 300ms`) => close overlay
- edits made before closing are effective (no restore)

### Main overlay (property selector)

- `NAV turn` => move row focus (`Channel` <-> `CC`)
- `OPT turn` => live edit focused value
- `NAV press` => open value selector for focused row
- `LEFT_TOP release` => close overlay only (no rollback)

### Value selector overlay

- `NAV turn` => select value (wrap navigation)
- `NAV release` => validate selected value
- return to main property overlay
- rendering style: VirtualListSelectorOverlay

### Quick switch while overlay is open

- hold `LEFT_CENTER` + `NAV turn` => page selection mode
  - on release of `LEFT_CENTER`: apply selected page and return to MacroEdit on that page
- hold `LEFT_BOTTOM` + `NAV turn` => macro target selection mode
  - on release of `LEFT_BOTTOM`: switch editing target macro and return to MacroEdit rows/values of that macro

### Persistence policy

- live apply (state + behavior effective immediately)
- persistence mode: live (each user change is persisted through current state API)

---

## Framework Feasibility Check

Verified capabilities:

- long press binding exists (`ButtonBuilder::longPress(ms)`)
- per-scope input authority exists (OverlayManager + scope cleanup)
- encoder predicates exist (`buttons.pressed(buttonId)` for hold modifiers)
- overlay stacking exists but is single-level (current + previous)

Implication:

- implementation is feasible in app layer, but validation uncovered a framework-level press/release routing issue
- framework stabilization plan is tracked here:
  - `docs/memories/work/feature-ms-sequencer/framework-input-release-routing-plan-main-2026-02-19.md`

Constraint to respect:

- single-level overlay stack means we must avoid 3-deep nested overlays
- page/macro hold selectors are only enabled from MacroEdit main overlay (not from value selector)

---

## Target Architecture

## Overlay Type Review (final naming)

Validated naming to keep consistency with existing enum style and avoid ambiguity:

- `MACRO_EDIT`
  - main property overlay (Channel / CC)
- `MACRO_EDIT_SELECTOR`
  - value selector for the currently focused property
- `PAGE_SELECTOR`
  - page selector reused for hold-`LEFT_CENTER` flow
- `MACRO_EDIT_MACRO_SELECTOR`
  - macro target selector used during hold-`LEFT_BOTTOM`

Notes:

- We intentionally reuse `PAGE_SELECTOR` instead of adding `MACRO_EDIT_PAGE_SELECTOR` to limit enum churn.
- We keep one clear role per overlay type for deterministic cleanup at phase 6.

## A) Overlay types

Current:

- `MACRO_EDIT` exists
- `PAGE_SELECTOR` enum exists but is not fully wired in this flow

Target:

- keep `MACRO_EDIT` as main property overlay
- add `MACRO_EDIT_SELECTOR` for value selector
- add `MACRO_EDIT_MACRO_SELECTOR` for hold-`LEFT_BOTTOM` macro targeting
- use `PAGE_SELECTOR` for hold-`LEFT_CENTER` page targeting in this flow

## B) State

Extend `MacroEditState` with explicit sub-states:

- main edit state
  - `editingIndex`
  - `focusedRow`
  - `tempChannel`
  - `tempCC`
- value selector sub-state
  - `visible`
  - `editingRow`
  - `selectedIndex`
- transient open/release decision state
  - `openedByMacroIndex`
  - `openedAtMs`
  - `pendingOpenReleaseDecision`
- macro selector sub-state
  - `selectedMacroIndex`

Page selector source remains `CoreState.pages.selector`.

## C) Rendering

MacroEdit main is rendered with `VirtualListKeyValueOverlay`:

- title: `MACRO <n>`
- meta: `PAGE <n>`
- rows:
  - `Channel` => `1..16`
  - `CC` => `0..127`

Selectors rendered with `VirtualListSelectorOverlay`:

- value selector (CH or CC values)
- page selector (Page 1..8)
- macro selector (Macro 1..8)

---

## Implementation Phases (methodical + testable)

### Phase 1 - Overlay plumbing and state model

Files:

- `midi-studio/core/src/ui/OverlayTypes.hpp`
- `midi-studio/core/src/state/MacroEditState.hpp`
- `midi-studio/core/src/state/CoreState.hpp`
- `midi-studio/core/src/context/StandaloneContext.hpp`

Actions:

- add overlay enum values for new selectors
- register new overlay visibility signals in CoreState overlay stack
- add new overlay members and watchers in StandaloneContext header
- define MacroEditState sub-states and reset behavior

Gate checks:

- compile: `ms build core --target native`
- no behavior change yet expected
- add inline `// LEGACY_CLEANUP_PHASE6` comments on transitional blocks that are kept temporarily

### Phase 2 - Rendering migration to VirtualList

Files:

- `midi-studio/core/src/context/StandaloneContext.cpp`

Actions:

- replace legacy `MacroEditOverlay` creation by `VirtualListKeyValueOverlay`
- create selector overlays (`MACRO_EDIT_SELECTOR`, `PAGE_SELECTOR`, `MACRO_EDIT_MACRO_SELECTOR`)
- wire `registerCleanup` and rendering watchers
- implement:
  - `renderMacroEdit()`
  - `renderMacroEditSelector()`
  - `renderMacroPageSelector()`
  - `renderMacroTargetSelector()`

Gate checks:

- compile: `ms build core --target native`
- smoke UI: open/close overlays from debug trigger if needed

### Phase 3 - MacroEdit handler core behavior

Files:

- `midi-studio/core/src/handler/macro/MacroEditHandler.hpp`
- `midi-studio/core/src/handler/macro/MacroEditHandler.cpp`

Actions:

- switch open trigger from `press()` to `longPress(500)`
- implement open release-window logic (`300ms`)
- implement main overlay controls:
  - NAV turn focus row
  - OPT turn live edit focused value
  - NAV press open value selector
  - LEFT_TOP close (no restore)
- apply edits live via `CoreState::setMacroConfig(...)`

Gate checks:

- compile: `ms build core --target native`
- manual checks:
  - long press opens main overlay
  - quick release keeps it open
  - late release closes
  - OPT live changes visible and effective

### Phase 4 - Value selector behavior

Files:

- `midi-studio/core/src/handler/macro/MacroEditHandler.cpp`

Actions:

- open selector on NAV press from main
- NAV turn in selector with wrap
- NAV release validate and return to main
- ensure selector shows correct domain by focused row:
  - Channel: 16 choices (display 1..16, stored 0..15)
  - CC: 128 choices (0..127)

Gate checks:

- compile: `ms build core --target native`
- manual checks:
  - selector opens from NAV press
  - selected value is applied on NAV release
  - returns to main overlay correctly

### Phase 5 - Hold modifiers (page and macro switching)

Files:

- `midi-studio/core/src/handler/macro/MacroEditHandler.cpp`

Actions:

- add `LEFT_CENTER` hold mode:
  - open page selector on press
  - NAV turn while held navigates page candidate
  - apply switch on LEFT_CENTER release
- add `LEFT_BOTTOM` hold mode:
  - open macro selector on press
  - NAV turn while held navigates macro candidate
  - apply edit-target switch on LEFT_BOTTOM release
- guard: only available from MacroEdit main (not from value selector)

Gate checks:

- compile: `ms build core --target native`
- manual checks:
  - hold LEFT_CENTER changes page selection flow correctly
  - hold LEFT_BOTTOM changes edited macro target correctly

### Phase 6 - Legacy cleanup + final validation

Files:

- `midi-studio/core/src/ui/macro/MacroEditOverlay.hpp`
- `midi-studio/core/src/ui/macro/MacroEditOverlay.cpp`
- includes/usages in context files

Actions:

- remove/de-wire old MacroEditOverlay implementation
- finalize comments/docs around new flow
- remove all `LEGACY_CLEANUP_PHASE6` markers introduced during migration

Gate checks:

- compile: `ms build core --target native`
- full manual end-to-end validation checklist

---

## End-to-End Validation Checklist (DoD)

1. `MACRO_3` long press opens MacroEdit main (properties CH/CC).
2. quick release after open keeps overlay open.
3. late release after open closes overlay.
4. NAV turn moves row focus.
5. OPT turn edits focused value live.
6. NAV press opens value selector.
7. NAV turn in selector wraps through values.
8. NAV release validates value and returns to main.
9. LEFT_TOP closes overlay without rollback.
10. hold LEFT_CENTER + NAV turn selects page; release applies page.
11. hold LEFT_BOTTOM + NAV turn selects macro; release applies macro target.
12. After close/reopen, values are effective and persisted per live policy.

---

## Risks and Mitigations

- accidental close from opener button release while user is editing
  - mitigation: strict `pendingOpenReleaseDecision` window logic

- overlay conflicts between main/value/page/macro selectors
  - mitigation: explicit state guards and one-level stack discipline

- high write frequency due to live persistence
  - mitigation: monitor storage load; if needed add tiny commit debounce in a follow-up

---

## Rollout Strategy

- implement phase-by-phase with build gate each phase
- run targeted manual checks after each phase
- only then extend the same interaction model to Sequencer Step Edit

---

## Implementation Trace Log

Use this section to track exactly what changed, phase by phase.

### Phase status

- [x] Phase 1 - Overlay plumbing and state model
- [x] Phase 2 - Rendering migration to VirtualList
- [x] Phase 3 - MacroEdit handler core behavior
- [x] Phase 4 - Value selector behavior
- [x] Phase 5 - Hold modifiers (page and macro switching)
- [ ] Phase 6 - Legacy cleanup + final validation

### Change journal

- 2026-02-19 - Plan v2 aligned with final UX contract (long press + release window, live apply, hold selectors).
- 2026-02-19 - Phase 1 implemented in core: new overlay enum types, MacroEditState sub-states, CoreState overlay registrations, legacy cleanup markers added (`LEGACY_CLEANUP_PHASE6`).
- 2026-02-19 - Phase 1 build gate passed: `ms build core --target native`.
- 2026-02-19 - Phase 2 implemented in core: MacroEdit migrated to `VirtualListKeyValueOverlay`, added `MACRO_EDIT_SELECTOR` / `PAGE_SELECTOR` / `MACRO_EDIT_MACRO_SELECTOR` render pipelines, and StandaloneContext overlay plumbing completed.
- 2026-02-19 - Phase 2 build gate passed: `ms build core --target native`.
- 2026-02-19 - Phase 3 implemented in core: MacroEdit handler refactored to long-press open (`500ms`), release-window decision (`300ms`), NAV focus + OPT live edit, and LEFT_TOP close without rollback.
- 2026-02-19 - Phase 4 implemented in core: NAV press opens value selector, NAV turn wraps values, NAV release applies and returns to main overlay.
- 2026-02-19 - Phase 3/4 build gate passed: `ms build core --target native`.
- 2026-02-19 - Phase 5 implemented in core: hold `LEFT_CENTER` opens page selector with NAV navigation and apply-on-release; hold `LEFT_BOTTOM` opens macro target selector with NAV navigation and apply-on-release.
- 2026-02-19 - Legacy cleanup executed: removed `src/ui/macro/MacroEditOverlay.hpp` and `src/ui/macro/MacroEditOverlay.cpp` (no remaining references).
- 2026-02-19 - Post-cleanup build gate passed: `ms build core --target native`.
- 2026-02-19 - Dedicated framework plan added for release-routing stabilization and linked from this refactor plan.
- 2026-02-19 - Framework routing phases F1-F4 implemented and integrated (`OwnerOnly` policy enabled in midi-studio input config).
- 2026-02-19 - MacroEdit handler adjusted to use press-owner handoff for selector/page/macro hold flows (`buttons.setPressOwner(...)`) and open-release timing now stamps when overlay becomes visible.

### Divergence log

- 2026-02-19 - Deferred StandaloneContext member/watcher additions for new MacroEdit selector overlays to Phase 2 (where rendering migration is implemented), to keep Phase 1 behavior-neutral and compile-safe.
- 2026-02-19 - Divergence resolved in Phase 2 (member/watcher additions implemented as planned).
- 2026-02-19 - New divergence discovered in validation: owner/release routing across authority changes requires framework-level fix. Tracked in `framework-input-release-routing-plan-main-2026-02-19.md`.
