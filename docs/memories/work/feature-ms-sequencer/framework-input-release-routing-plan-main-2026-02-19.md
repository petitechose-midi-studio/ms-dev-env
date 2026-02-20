# Implementation Plan - Framework Input Release Routing (main)

Date: 2026-02-19
Status: Active
Owner: open-control/framework + midi-studio/core integration

## Context

During MacroEdit VirtualList validation on `midi-studio/core`, several interaction bugs were observed:

- quick/late release decision feels offset from visible overlay timing
- `NAV` value selector appears to not open reliably
- `LEFT_TOP` close can be ignored in some paths
- hold selectors (`LEFT_CENTER`, `LEFT_BOTTOM`) appear to open/apply inconsistently

Root cause analysis points to **press/release routing across authority changes** in the framework input engine.
When a `PRESS` opens a new overlay (authority switch), the paired `RELEASE` may be dispatched through fallback in the new scope.

## Scope

In scope:

- `open-control/framework/src/oc/core/input`
- `open-control/framework/src/oc/core/input/InputConfig.hpp`
- `open-control/framework/test/test_inputbinding`
- `midi-studio/core/src/config/App.hpp` (policy opt-in)

Out of scope (for this pass):

- redesign of overlay stack model
- app-level gesture redesign unrelated to ownership routing

---

## Objectives

1. Make button `RELEASE` routing deterministic after scoped `PRESS`.
2. Preserve backward compatibility by default.
3. Allow product-level strict mode to block cross-scope release fallback.
4. Reduce app-side guard hacks in macro/sequencer handlers.

---

## Current Code Hotspots

- `open-control/framework/src/oc/core/input/InputBinding.cpp:180` (`onButtonRelease`)
- `open-control/framework/src/oc/core/input/InputBinding.cpp:214` (`handleScopedRelease`)
- `open-control/framework/src/oc/core/input/InputBinding.cpp:338` (`dispatchReleaseToScope`)
- `open-control/framework/src/oc/core/input/InputBinding.cpp:250` (`dispatchButtonEvent` fallback)

The authority check currently applied inside `dispatchReleaseToScope(...)` for owner-driven release handling is the critical point.

---

## Proposed Design

## A) Add release routing policy to InputConfig

File:

- `open-control/framework/src/oc/core/input/InputConfig.hpp`

Add:

- `enum class ReleaseRoutingPolicy : uint8_t { OwnerThenFallback, OwnerOnly };`
- new config field:
  - `ReleaseRoutingPolicy releaseRoutingPolicy = ReleaseRoutingPolicy::OwnerThenFallback;`

Compatibility:

- default remains legacy-safe behavior (`OwnerThenFallback`).

## B) Owner-driven release dispatch that can bypass authority

Files:

- `open-control/framework/src/oc/core/input/InputBinding.hpp`
- `open-control/framework/src/oc/core/input/InputBinding.cpp`

Changes:

- extend internal release dispatch path with an authority mode for owner routing.
- owner-paired release should be dispatchable to owner scope even if overlay authority changed since press.

Expected behavior by policy:

- `OwnerThenFallback`:
  - try owner release handler first
  - if no owner release binding matched, allow fallback release dispatch (current broad behavior)
- `OwnerOnly`:
  - try owner release handler first
  - if no owner release binding matched, consume/stop (no cross-scope fallback)

## C) Product opt-in in midi-studio

File:

- `midi-studio/core/src/config/App.hpp`

Change:

- set
  - `.releaseRoutingPolicy = oc::core::input::ReleaseRoutingPolicy::OwnerOnly`
  in `Config::Input::CONFIG`.

Rationale:

- MacroEdit/Sequencer overlays rely heavily on strict press/release pairing.

---

## Optional Extension (deferred unless needed)

Add per-binding override in framework:

- `ButtonBinding` flag (e.g. `consumeRelease`)
- fluent API in `ButtonBuilder` (e.g. `.consumeRelease()`)

Use only if global policy + owner dispatch is not sufficient for edge flows.

---

## Implementation Phases (testable)

### Phase F1 - Config + internal API wiring

Actions:

- add `ReleaseRoutingPolicy` to `InputConfig`
- plumb policy usage in `InputBinding` release path
- add internal helper signature changes as needed

Gate:

- framework compiles (`pio test -e native`)

### Phase F2 - Core behavior change in InputBinding

Actions:

- implement owner release dispatch path that can bypass authority checks
- implement policy branch (`OwnerThenFallback` vs `OwnerOnly`)

Gate:

- `pio test -e native` passes

### Phase F3 - Unit tests for routing semantics

File:

- `open-control/framework/test/test_inputbinding/test_inputbinding.cpp`

Add tests:

1. owner release still triggers when authority changed after press
2. owner-only mode blocks cross-scope release fallback
3. owner-then-fallback keeps legacy behavior
4. long-press + owner-only does not regress existing latch behavior

Gate:

- new and existing tests pass

### Phase F4 - midi-studio integration

Actions:

- set `OwnerOnly` policy in `midi-studio/core/src/config/App.hpp`
- re-run macro edit manual matrix

Gate:

- `ms build core --target native`
- manual matrix for macro edit passes

### Phase F5 - Cleanup and follow-up

Actions:

- remove app-level temporary guards that become redundant
- document migration note in framework README if public behavior changed

Gate:

- no remaining workaround-only code in `MacroEditHandler`

---

## Validation Matrix (for macro flow)

1. long press opens MacroEdit main
2. quick release keeps overlay open
3. late release closes overlay
4. `NAV press` reliably opens value selector
5. `NAV release` applies value and returns
6. `LEFT_TOP` always closes
7. hold `LEFT_CENTER` page selector works end-to-end
8. hold `LEFT_BOTTOM` macro selector works end-to-end

---

## Risks and Mitigations

- Risk: behavior change for apps depending on fallback side-effects
  - Mitigation: default policy stays legacy (`OwnerThenFallback`)

- Risk: hidden regressions in latch/release combinations
  - Mitigation: extend existing inputbinding test suite before integration

- Risk: overfitting to macro flow
  - Mitigation: tests target generic owner-routing semantics, not app specifics

---

## Trace Log

### Phase status

- [x] F1 - Config + internal API wiring
- [x] F2 - Core behavior change in InputBinding
- [x] F3 - Unit tests for routing semantics
- [x] F4 - midi-studio integration
- [ ] F5 - Cleanup and follow-up

### Change journal

- 2026-02-19 - Plan created after MacroEdit validation uncovered owner/release routing issues.
- 2026-02-19 - F1 implemented: added `ReleaseRoutingPolicy` to `InputConfig` (default `OwnerThenFallback`).
- 2026-02-19 - F2 implemented: owner-scoped release dispatch now supports authority bypass for owner-paired release path; policy branch added for fallback behavior.
- 2026-02-19 - F3 implemented: added 5 unit tests in `test_inputbinding` covering authority switch, owner-only fallback blocking, legacy fallback compatibility, latch cycle non-regression, and explicit press-owner handoff.
- 2026-02-19 - Framework test gates passed: `pio test -e native -f test_inputbinding` and full `pio test -e native`.
- 2026-02-19 - F4 implemented in midi-studio: set `.releaseRoutingPolicy = ReleaseRoutingPolicy::OwnerOnly` in `src/config/App.hpp`; build gate passed (`ms build core --target native`).
- 2026-02-19 - Added framework API `setPressOwner(button, scope)` (`InputBinding` + `ButtonAPI`) to support deterministic release handoff after scope transition on press.

### Divergence log

- (empty)
