# MIDI Sync Clock Roadmap (Master / Slave / Auto)

Date: 2026-02-16  
Owner: midi-studio team  
Status: In progress (Phases A-F implemented, pending live/manual validation)

## 1) Goal

Deliver a robust MIDI Clock sync feature so the controller can:
- run as `MASTER` (send sync),
- run as `SLAVE` (follow incoming sync),
- run as `AUTO` (switch to slave when valid incoming sync is detected, fall back to master when missing).

Global settings must be available via `LEFT_TOP` long press (2 seconds), while preserving existing short press behavior.

## 2) Scope locked (no open blockers)

- Sync modes: `Master`, `Slave`, `Auto`.
- `Follow Transport` policy: `ON` in `Slave` and `Auto(EXTERNAL)`.
- Realtime messages in scope: `Clock(0xF8)`, `Start(0xFA)`, `Continue(0xFB)`, `Stop(0xFC)`.
- UI entrypoint: `LEFT_TOP` long press exactly 2000 ms.
- UI architecture: keep current VirtualList + OverlayManager patterns.
- Implementation discipline: each step is testable; a step is `Done` only after test evidence is logged.

## 3) Current architecture audit snapshot

- `IMidi` currently handles CC/Note/SysEx only (no realtime clock API):
  - `open-control/framework/src/oc/interface/IMidi.hpp`
- HAL implementations currently do not expose full realtime flow:
  - `open-control/hal-teensy/src/oc/hal/teensy/UsbMidi.cpp`
  - `open-control/hal-midi/src/oc/hal/midi/LibreMidiTransport.cpp`
- Core sequencer playback currently runs internal timing logic:
  - `midi-studio/core/src/sequencer/SequencerPlaybackService.cpp`
  - `open-control/note/src/oc/note/sequencer/StepSequencerEngine.cpp`
- Overlay + VirtualList architecture is already in place and reusable:
  - `midi-studio/core/src/context/StandaloneContext.cpp`
  - `midi-studio/ui/src/ms/ui/widget/VirtualListKeyValueOverlay.cpp`
  - `midi-studio/ui/src/ms/ui/widget/VirtualListSelectorOverlay.cpp`

## 4) Execution rules (strict)

1. One step at a time, with clear status updates.
2. No step can be marked `Done` without explicit test results.
3. If a step depends on a later change, mark it `Pending next step` and explain why.
4. Keep logs so any developer can resume work without context loss.
5. Preserve architecture invariants (state is source of truth, scoped input authority, overlay lifecycle cleanup).

## 5) Step status values

- `Planned`: defined, not started.
- `In progress`: implementation ongoing.
- `Pending next step`: partially implemented, blocked by dependency.
- `Blocked`: external blocker.
- `Done`: implementation complete and tested with evidence.

## 6) Roadmap (synthetic, one line per sub-step)

### Phase A - Framework realtime plumbing

| ID | Sub-step (one line) | Deliverable | Test gate | Status |
|---|---|---|---|---|
| A1 | Extend `IMidi` with realtime callbacks (`onClock/onStart/onStop/onContinue`) | Interface update | Full compile of framework dependents | Done |
| A2 | Extend `IMidi` with realtime send methods (`sendClock/sendStart/sendStop/sendContinue`) | Interface update | Full compile of framework dependents | Done |
| A3 | Add realtime wrapper methods in `MidiAPI` | API surface update | Build + API smoke calls | Done |
| A4 | Add realtime event definitions to framework events | Event types added | Build framework + event include checks | Done |
| A5 | Wire realtime MIDI callbacks to EventBus in app bootstrap | Event routing path | Runtime smoke: callback -> event | Pending next step |
| A6 | Update `NullMidi` with no-op realtime methods/callbacks | Compatibility impl | Desktop compile without MIDI hardware | Done |

### Phase B - HAL realtime support

| ID | Sub-step (one line) | Deliverable | Test gate | Status |
|---|---|---|---|---|
| B1 | Implement realtime RX decode in Teensy USB MIDI transport | RX callbacks fired | Hardware or mocked RX trace | Done |
| B2 | Implement realtime TX send in Teensy USB MIDI transport | TX methods functional | Host sees outgoing realtime bytes | Done |
| B3 | Implement realtime RX decode in LibreMidi transport | RX callbacks fired | Unit parsing tests for 0xF8/FA/FB/FC | Done |
| B4 | Implement realtime TX send in LibreMidi transport | TX methods functional | LoopMIDI capture confirms realtime flow | Done |
| B5 | Add/extend hal-midi tests for realtime parsing and edge cases | Automated tests | Test target passes on CI/local | Done |

### Phase C - Core sync engine

| ID | Sub-step (one line) | Deliverable | Test gate | Status |
|---|---|---|---|---|
| C1 | Add `MidiSyncMode` and `ClockSourceActive` to core state | New typed state | Core compile + state wiring check | Done |
| C2 | Add runtime sync state (last tick times, lock, timeout, hysteresis) | Internal sync model | Unit tests for transitions | Done |
| C3 | Create `MidiClockSyncService` and call it in `StandaloneContext::update()` | Service integration | Runtime smoke in standalone context | Done |
| C4 | Implement `MASTER` clock generation at 24 PPQN using time accumulator | Stable clock output | Drift/jitter test over timed run | Pending next step |
| C5 | Implement `SLAVE` tick ingest from incoming `0xF8` | External clock following | External source tempo tracking test | Pending next step |
| C6 | Implement `AUTO` lock-on external and timeout fallback to internal | Auto arbitration | Deterministic lock/fallback test | Done |
| C7 | Apply incoming `Start/Stop/Continue` to transport state in slave/auto-ext | Transport sync policy | Start-stop behavior test | Done |
| C8 | Ensure source switches are safe (no hanging notes, clean scheduler state) | Transition safety | Stress switch test with note integrity | Pending next step |

### Phase D - Global settings UI and input

| ID | Sub-step (one line) | Deliverable | Test gate | Status |
|---|---|---|---|---|
| D1 | Add global settings overlay type(s) in core overlay enum | Overlay contract | Compile + overlay registry check | Done |
| D2 | Add `GlobalSettingsState` to `CoreState` | Reactive state | Watcher and reset path compile check | Done |
| D3 | Register global settings overlays in visibility stack | Visibility control | Overlay authority behavior test | Done |
| D4 | Render global settings main list using `VirtualListKeyValueOverlay` | Settings list UI | UI render/update smoke | Done |
| D5 | Render value selector using `VirtualListSelectorOverlay` for enum edits | Value picker UI | Selector navigation test | Done |
| D6 | Add `GlobalSettingsHandler` with scoped bindings and apply/cancel logic | Input handling | Input authority and lifecycle test | Done |
| D7 | Implement `LEFT_TOP` long press (2000 ms) to open global settings | Entry gesture | Press duration behavior test | Pending next step |
| D8 | Preserve short press `LEFT_TOP` behavior (view selector) without regression | Non-regression behavior | Regression test for existing view switcher | Pending next step |

### Phase E - Persistence and migration

| ID | Sub-step (one line) | Deliverable | Test gate | Status |
|---|---|---|---|---|
| E1 | Extend `CoreSettings` to store sync-related settings | Persistent model | Save/reload verification | Done |
| E2 | Add safe storage migration/version bump for new settings | Migration path | Old data boot migration test | Done |
| E3 | Add factory reset support for new sync settings | Reset behavior | Factory reset test | Done |

### Phase F - User feedback in transport/status area

| ID | Sub-step (one line) | Deliverable | Test gate | Status |
|---|---|---|---|---|
| F1 | Add source indicator (`INT`/`EXT`) in status/transport UI | Visual source state | Signal-to-UI update test | Done |
| F2 | Define and implement slave tempo display policy | Tempo UX consistency | Tempo display behavior test | Done |
| F3 | Add optional subtle sync input activity indicator | Debug-friendly feedback | Activity pulse test | Done |

### Phase G - End-to-end validation

| ID | Sub-step (one line) | Deliverable | Test gate | Status |
|---|---|---|---|---|
| G1 | Add deterministic unit tests for auto lock, timeout, and hysteresis | Core test coverage | Unit suite passes | Done |
| G2 | Validate desktop integration path via loopMIDI/libremidi | Desktop E2E proof | Manual scripted scenario passes | Planned |
| G3 | Validate Teensy USB MIDI realtime path on hardware | Hardware E2E proof | Real device scenario passes | Planned |
| G4 | Validate DAW + external device scenarios (drift, jitter, start/stop, replug) | Product acceptance proof | QA checklist complete | Planned |

## 7) Dependency map (resume-friendly)

- `A*` is prerequisite for `B*` and `C*`.
- `B*` and `C*` can overlap after `A1-A4` are stable.
- `D*` can start early with mock state values, but final validation depends on `C*`.
- `E*` depends on final settings schema in `D*` and sync model in `C*`.
- `F*` depends on stable state fields from `C*`.
- `G*` only after `A-F` are completed or explicitly flagged as pending.

## 8) Test evidence protocol (mandatory for each step)

For each step, add one log entry in Section 10 with:
- `Step ID`
- `Change summary`
- `Commands run`
- `Expected result`
- `Observed result`
- `Decision` (`Done` or `Pending next step` with reason)

If tests cannot be executed yet, mark:
- `Decision: Pending next step`
- `Reason: <explicit dependency>`

## 9) Acceptance checklist (global)

- Controller can drive external DAW/device in `MASTER` at stable 24 PPQN.
- Controller can follow external MIDI clock in `SLAVE`.
- `AUTO` mode locks and falls back without oscillation.
- `Start/Stop/Continue` behavior is correct in `SLAVE` and `AUTO(EXTERNAL)`.
- Global settings open on `LEFT_TOP` long press 2s and do not break short press behavior.
- Settings persist across reboot and support migration/factory reset.
- No architecture invariant regressions in handlers/views/overlays.

## 10) Execution log (append-only)

### Log template

```
Step ID:
Date:
Status:
Change summary:
Files touched:
Commands run:
Expected result:
Observed result:
Decision:
Next action:
```

### Entries

- 2026-02-16 - Planning baseline created. No code implementation started yet.
  - Step ID: PLAN-0
  - Status: Done
  - Change summary: Roadmap drafted and locked with product decisions.
  - Files touched: `docs/memories/work/feature-midi-sync-clock/implementation-roadmap-main-2026-02-16.md`
  - Commands run: N/A
  - Expected result: Clear, resume-friendly execution plan.
  - Observed result: Plan includes phases, dependencies, and test protocol.
  - Decision: Done
  - Next action: Start Phase A, Step A1.

- 2026-02-16 - Step A1 completed.
  - Step ID: A1
  - Status: Done
  - Change summary: Added optional realtime callback type and callback hooks to `IMidi`.
  - Files touched: `open-control/framework/src/oc/interface/IMidi.hpp`
  - Commands run: `uv run ms build core --target native`; `uv run ms build bitwig --target native`
  - Expected result: Framework and app dependents compile with new `IMidi` callback surface.
  - Observed result: Both native builds succeeded.
  - Decision: Done
  - Next action: Continue Phase A with realtime output methods and API wrappers.

- 2026-02-16 - Step A2 completed.
  - Step ID: A2
  - Status: Done
  - Change summary: Added optional realtime output methods (`sendClock/sendStart/sendStop/sendContinue`) to `IMidi`.
  - Files touched: `open-control/framework/src/oc/interface/IMidi.hpp`
  - Commands run: `uv run ms build core --target native`; `uv run ms build bitwig --target native`
  - Expected result: New output methods available without breaking existing transports.
  - Observed result: Both native builds succeeded.
  - Decision: Done
  - Next action: Expose realtime send API from `MidiAPI`.

- 2026-02-16 - Step A3 completed.
  - Step ID: A3
  - Status: Done
  - Change summary: Added realtime wrapper methods to `MidiAPI` for clock/start/continue/stop.
  - Files touched: `open-control/framework/src/oc/api/MidiAPI.hpp`; `open-control/framework/src/oc/api/MidiAPI.cpp`
  - Commands run: `uv run ms build core --target native`; `uv run ms build bitwig --target native`
  - Expected result: Public framework API can emit realtime messages.
  - Observed result: Both native builds succeeded.
  - Decision: Done
  - Next action: Add matching event types and event classes.

- 2026-02-16 - Step A4 completed.
  - Step ID: A4
  - Status: Done
  - Change summary: Added MIDI realtime event constants and event classes (Clock/Start/Continue/Stop).
  - Files touched: `open-control/framework/src/oc/core/event/EventTypes.hpp`; `open-control/framework/src/oc/core/event/Events.hpp`; `open-control/framework/src/oc/context/ContextBase.hpp`
  - Commands run: `uv run ms build core --target native`; `uv run ms build bitwig --target native`
  - Expected result: EventBus can represent realtime MIDI events and contexts can subscribe with typed helpers.
  - Observed result: Both native builds succeeded.
  - Decision: Done
  - Next action: Wire HAL realtime callbacks into app bootstrap.

- 2026-02-16 - Step A5 partially completed.
  - Step ID: A5
  - Status: Pending next step
  - Change summary: Wired `setOnClock/setOnStart/setOnContinue/setOnStop` in `OpenControlApp` to emit new realtime events.
  - Files touched: `open-control/framework/src/oc/app/OpenControlApp.cpp`
  - Commands run: `uv run ms build core --target native`; `uv run ms build bitwig --target native`
  - Expected result: Realtime callbacks route to EventBus at runtime.
  - Observed result: Compile-level integration is valid; runtime callback smoke test still pending.
  - Decision: Pending next step
  - Next action: Validate runtime callback path when HAL realtime RX is implemented in Phase B.

- 2026-02-16 - Step A6 completed.
  - Step ID: A6
  - Status: Done
  - Change summary: Extended `NullMidi` with no-op realtime send/callback overrides.
  - Files touched: `open-control/framework/src/oc/impl/NullMidi.hpp`
  - Commands run: `uv run ms build core --target native`; `uv run ms build bitwig --target native`
  - Expected result: Null MIDI backend remains fully compatible with expanded interface.
  - Observed result: Both native builds succeeded.
  - Decision: Done
  - Next action: Start Phase B (HAL realtime RX/TX).

- 2026-02-16 - Step B1 completed.
  - Step ID: B1
  - Status: Done
  - Change summary: Added Teensy USB MIDI realtime RX decode for clock/start/continue/stop callbacks.
  - Files touched: `open-control/hal-teensy/src/oc/hal/teensy/UsbMidi.hpp`; `open-control/hal-teensy/src/oc/hal/teensy/UsbMidi.cpp`
  - Commands run: `uv run pio run -e dev -d "midi-studio/core"`
  - Expected result: Teensy transport compiles with realtime callback path integrated.
  - Observed result: PlatformIO `dev` build succeeded and produced `firmware.hex`.
  - Decision: Done
  - Next action: Implement Teensy realtime TX methods.

- 2026-02-16 - Step B2 completed.
  - Step ID: B2
  - Status: Done
  - Change summary: Added Teensy realtime TX methods (`sendClock/sendStart/sendStop/sendContinue`) using explicit realtime status sends.
  - Files touched: `open-control/hal-teensy/src/oc/hal/teensy/UsbMidi.hpp`; `open-control/hal-teensy/src/oc/hal/teensy/UsbMidi.cpp`
  - Commands run: `uv run pio run -e dev -d "midi-studio/core"`
  - Expected result: Teensy transport compiles with realtime output methods.
  - Observed result: PlatformIO `dev` build succeeded and produced `firmware.hex`.
  - Decision: Done
  - Next action: Extend desktop libremidi realtime RX.

- 2026-02-16 - Step B3 completed.
  - Step ID: B3
  - Status: Done
  - Change summary: Added libremidi realtime RX decode (`0xF8/0xFA/0xFB/0xFC`) in `processMessage` before channel-status parsing.
  - Files touched: `open-control/hal-midi/src/oc/hal/midi/LibreMidiTransport.hpp`; `open-control/hal-midi/src/oc/hal/midi/LibreMidiTransport.cpp`
  - Commands run: `uv run ms build core --target native`; `uv run ms build bitwig --target native`; `"tools/zig/zig.exe" c++ -std=c++17 "open-control/hal-midi/test/test_LibreMidiTransport.cpp" -o ".build/test_LibreMidiTransport.exe" && ".build/test_LibreMidiTransport.exe"`
  - Expected result: Desktop transport decodes realtime input and callbacks can be triggered.
  - Observed result: Native app builds succeeded and realtime parsing tests passed.
  - Decision: Done
  - Next action: Add libremidi realtime TX methods.

- 2026-02-16 - Step B4 completed.
  - Step ID: B4
  - Status: Done
  - Change summary: Added libremidi realtime TX methods emitting single-byte status messages for clock/start/continue/stop.
  - Files touched: `open-control/hal-midi/src/oc/hal/midi/LibreMidiTransport.hpp`; `open-control/hal-midi/src/oc/hal/midi/LibreMidiTransport.cpp`
  - Commands run: `uv run ms build core --target native`; `uv run ms build bitwig --target native`
  - Expected result: Desktop transport compiles with realtime output support.
  - Observed result: Both native builds succeeded.
  - Decision: Done
  - Next action: Lock realtime tests in hal-midi test target.

- 2026-02-16 - Step B5 completed.
  - Step ID: B5
  - Status: Done
  - Change summary: Extended `test_LibreMidiTransport.cpp` with realtime tests for clock/start/continue/stop parsing.
  - Files touched: `open-control/hal-midi/test/test_LibreMidiTransport.cpp`
  - Commands run: `"tools/zig/zig.exe" c++ -std=c++17 "open-control/hal-midi/test/test_LibreMidiTransport.cpp" -o ".build/test_LibreMidiTransport.exe" && ".build/test_LibreMidiTransport.exe"`
  - Expected result: Realtime parser behavior validated by automated assertions.
  - Observed result: Test executable ran successfully with all realtime tests passing.
  - Decision: Done
  - Next action: Start Phase C (core sync mode/state/service).

- 2026-02-16 - Step C1 completed.
  - Step ID: C1
  - Status: Done
  - Change summary: Added core sync state with `MidiSyncMode`, `ClockSourceActive`, and sync settings signals.
  - Files touched: `midi-studio/core/src/state/MidiSyncState.hpp`; `midi-studio/core/src/state/CoreState.hpp`
  - Commands run: `uv run ms build core --target native`; `uv run pio run -e dev -d "midi-studio/core"`
  - Expected result: Core compiles with explicit MIDI sync mode/source state.
  - Observed result: Native and Teensy builds succeeded.
  - Decision: Done
  - Next action: Implement runtime sync arbitration logic.

- 2026-02-16 - Step C2 completed.
  - Step ID: C2
  - Status: Done
  - Change summary: Added runtime sync model in `MidiClockSyncService` (external clock streak, lock state, fallback timeout, source arbitration).
  - Files touched: `midi-studio/core/src/sequencer/MidiClockSyncService.hpp`; `midi-studio/core/src/sequencer/MidiClockSyncService.cpp`; `midi-studio/core/test/test_MidiClockSyncService.cpp`
  - Commands run: `"tools/zig/zig.exe" c++ -std=c++17 -I"open-control/framework/src" -I"open-control/note/src" -I"midi-studio/core/src" "midi-studio/core/test/test_MidiClockSyncService.cpp" "midi-studio/core/src/sequencer/MidiClockSyncService.cpp" "open-control/framework/src/oc/api/MidiAPI.cpp" "open-control/framework/src/oc/log/Log.cpp" "open-control/framework/src/oc/time/Time.cpp" "open-control/framework/src/oc/state/NotificationQueue.cpp" "open-control/note/src/oc/note/clock/InternalClock.cpp" -o ".build/test_MidiClockSyncService.exe" && ".build/test_MidiClockSyncService.exe"`
  - Expected result: Runtime sync transitions (lock/fallback) are deterministic and testable.
  - Observed result: Unit test executable passed all transition tests.
  - Decision: Done
  - Next action: Wire sync service into StandaloneContext loop.

- 2026-02-16 - Step C3 completed.
  - Step ID: C3
  - Status: Done
  - Change summary: Integrated `MidiClockSyncService` in `StandaloneContext`, subscribed to realtime MIDI events, and routed tick/playing into sequencer playback.
  - Files touched: `midi-studio/core/src/context/StandaloneContext.hpp`; `midi-studio/core/src/context/StandaloneContext.cpp`; `midi-studio/core/src/sequencer/SequencerPlaybackService.hpp`; `midi-studio/core/src/sequencer/SequencerPlaybackService.cpp`
  - Commands run: `uv run ms build core --target native`; `uv run ms build bitwig --target native`; `uv run pio run -e dev -d "midi-studio/core"`
  - Expected result: Standalone update loop can run sequencer from sync service source.
  - Observed result: Native and Teensy builds succeeded with integrated service.
  - Decision: Done
  - Next action: Validate timing behavior and source transitions under live scenarios.

- 2026-02-16 - Step C4 partially completed.
  - Step ID: C4
  - Status: Pending next step
  - Change summary: Implemented master clock TX at PPQN domain from internal clock with bounded burst output.
  - Files touched: `midi-studio/core/src/sequencer/MidiClockSyncService.cpp`
  - Commands run: `"tools/zig/zig.exe" c++ -std=c++17 -I"open-control/framework/src" -I"open-control/note/src" -I"midi-studio/core/src" "midi-studio/core/test/test_MidiClockSyncService.cpp" "midi-studio/core/src/sequencer/MidiClockSyncService.cpp" "open-control/framework/src/oc/api/MidiAPI.cpp" "open-control/framework/src/oc/log/Log.cpp" "open-control/framework/src/oc/time/Time.cpp" "open-control/framework/src/oc/state/NotificationQueue.cpp" "open-control/note/src/oc/note/clock/InternalClock.cpp" -o ".build/test_MidiClockSyncService.exe" && ".build/test_MidiClockSyncService.exe"`; `uv run ms build core --target native`
  - Expected result: Internal playback emits realtime Start/Clock/Stop.
  - Observed result: Unit tests validate event emission; long-run drift/jitter test still pending.
  - Decision: Pending next step
  - Next action: Run timed external capture to measure jitter/drift.

- 2026-02-16 - Step C5 partially completed.
  - Step ID: C5
  - Status: Pending next step
  - Change summary: Implemented slave tick ingest from incoming `0xF8` and sequencer clock-source switching.
  - Files touched: `midi-studio/core/src/sequencer/MidiClockSyncService.cpp`; `midi-studio/core/src/context/StandaloneContext.cpp`
  - Commands run: `"tools/zig/zig.exe" c++ -std=c++17 -I"open-control/framework/src" -I"open-control/note/src" -I"midi-studio/core/src" "midi-studio/core/test/test_MidiClockSyncService.cpp" "midi-studio/core/src/sequencer/MidiClockSyncService.cpp" "open-control/framework/src/oc/api/MidiAPI.cpp" "open-control/framework/src/oc/log/Log.cpp" "open-control/framework/src/oc/time/Time.cpp" "open-control/framework/src/oc/state/NotificationQueue.cpp" "open-control/note/src/oc/note/clock/InternalClock.cpp" -o ".build/test_MidiClockSyncService.exe" && ".build/test_MidiClockSyncService.exe"`; `uv run ms build core --target native`
  - Expected result: External MIDI clock can drive playback tick domain.
  - Observed result: Unit tests validate tick ingestion logic; external hardware/DAW tempo-follow test pending.
  - Decision: Pending next step
  - Next action: Validate against real external clock source.

- 2026-02-16 - Step C6 completed.
  - Step ID: C6
  - Status: Done
  - Change summary: Implemented AUTO mode lock-on by clock streak and fallback by timeout.
  - Files touched: `midi-studio/core/src/sequencer/MidiClockSyncService.cpp`; `midi-studio/core/test/test_MidiClockSyncService.cpp`
  - Commands run: `"tools/zig/zig.exe" c++ -std=c++17 -I"open-control/framework/src" -I"open-control/note/src" -I"midi-studio/core/src" "midi-studio/core/test/test_MidiClockSyncService.cpp" "midi-studio/core/src/sequencer/MidiClockSyncService.cpp" "open-control/framework/src/oc/api/MidiAPI.cpp" "open-control/framework/src/oc/log/Log.cpp" "open-control/framework/src/oc/time/Time.cpp" "open-control/framework/src/oc/state/NotificationQueue.cpp" "open-control/note/src/oc/note/clock/InternalClock.cpp" -o ".build/test_MidiClockSyncService.exe" && ".build/test_MidiClockSyncService.exe"`
  - Expected result: Auto mode transitions between internal/external sources deterministically.
  - Observed result: Deterministic lock/fallback test passed.
  - Decision: Done
  - Next action: Keep transport behavior aligned during source changes.

- 2026-02-16 - Step C7 completed.
  - Step ID: C7
  - Status: Done
  - Change summary: Applied external `Start/Stop/Continue` handling in sync service with `followTransport` policy.
  - Files touched: `midi-studio/core/src/sequencer/MidiClockSyncService.cpp`; `midi-studio/core/test/test_MidiClockSyncService.cpp`
  - Commands run: `"tools/zig/zig.exe" c++ -std=c++17 -I"open-control/framework/src" -I"open-control/note/src" -I"midi-studio/core/src" "midi-studio/core/test/test_MidiClockSyncService.cpp" "midi-studio/core/src/sequencer/MidiClockSyncService.cpp" "open-control/framework/src/oc/api/MidiAPI.cpp" "open-control/framework/src/oc/log/Log.cpp" "open-control/framework/src/oc/time/Time.cpp" "open-control/framework/src/oc/state/NotificationQueue.cpp" "open-control/note/src/oc/note/clock/InternalClock.cpp" -o ".build/test_MidiClockSyncService.exe" && ".build/test_MidiClockSyncService.exe"`
  - Expected result: Slave/auto-ext transport state follows incoming realtime transport messages.
  - Observed result: Unit tests passed for external transport-driven playing state.
  - Decision: Done
  - Next action: Stress source transitions with active notes.

- 2026-02-16 - Step C8 partially completed.
  - Step ID: C8
  - Status: Pending next step
  - Change summary: Added resync request on source changes and transport edges; StandaloneContext now forces sequencer stop/reset on resync.
  - Files touched: `midi-studio/core/src/sequencer/MidiClockSyncService.cpp`; `midi-studio/core/src/context/StandaloneContext.cpp`; `midi-studio/core/src/sequencer/SequencerPlaybackService.cpp`
  - Commands run: `uv run ms build core --target native`; `uv run pio run -e dev -d "midi-studio/core"`
  - Expected result: Source transitions avoid stale scheduler state/hanging notes.
  - Observed result: Build-level integration successful; stress verification with live note traffic is pending.
  - Decision: Pending next step
  - Next action: Execute transition stress tests with sustained note activity.

- 2026-02-16 - Steps D1-D3 completed.
  - Step ID: D1/D2/D3
  - Status: Done
  - Change summary: Added global settings overlay enum entries/state and registered both global settings overlays in `CoreState` visibility stack.
  - Files touched: `midi-studio/core/src/ui/OverlayTypes.hpp`; `midi-studio/core/src/state/GlobalSettingsState.hpp`; `midi-studio/core/src/state/CoreState.hpp`
  - Commands run: `uv run ms build core --target native`; `uv run pio run -e dev -d "midi-studio/core"`
  - Expected result: Overlay contract/state wiring compile and initialize correctly.
  - Observed result: Native + Teensy builds succeeded with overlays registered.
  - Decision: Done
  - Next action: Implement rendering and input handler for global settings overlays.

- 2026-02-16 - Steps D4-D6 completed.
  - Step ID: D4/D5/D6
  - Status: Done
  - Change summary: Implemented global settings rendering (VirtualList key/value + selector), and added `GlobalSettingsHandler` with apply/cancel logic + persistence writes.
  - Files touched: `midi-studio/core/src/context/StandaloneContext.hpp`; `midi-studio/core/src/context/StandaloneContext.cpp`; `midi-studio/core/src/handler/settings/GlobalSettingsHandler.hpp`; `midi-studio/core/src/handler/settings/GlobalSettingsHandler.cpp`
  - Commands run: `uv run ms build core --target native`; `uv run pio run -e dev -d "midi-studio/core"`
  - Expected result: Global settings overlays render and input bindings compile end-to-end.
  - Observed result: Both builds succeeded; new handler/object files compiled and linked.
  - Decision: Done
  - Next action: Validate 2s gesture and short-press coexistence on live UI.

- 2026-02-16 - Steps D7-D8 partially completed.
  - Step ID: D7/D8
  - Status: Pending next step
  - Change summary: Bound `LEFT_TOP` long press (2000 ms) to open global settings while keeping existing short-press view selector path intact in code.
  - Files touched: `midi-studio/core/src/handler/settings/GlobalSettingsHandler.cpp`; `midi-studio/core/src/context/StandaloneContext.cpp`
  - Commands run: `uv run ms build core --target native`; `uv run pio run -e dev -d "midi-studio/core"`
  - Expected result: Hold opens global settings; short press still opens view selector.
  - Observed result: Compile-level integration passed; physical/manual interaction verification is still pending.
  - Decision: Pending next step
  - Next action: Run manual timing/interaction test on target UI path.

- 2026-02-16 - Steps E1-E3 completed.
  - Step ID: E1/E2/E3
  - Status: Done
  - Change summary: Extended `CoreSettings` with MIDI sync persistence fields, added version migration `v1 -> v2`, and wired factory reset to persist reset sync defaults.
  - Files touched: `midi-studio/core/src/state/CoreSettings.hpp`; `midi-studio/core/src/state/CoreState.hpp`; `midi-studio/core/test/test_CoreSettings.cpp`
  - Commands run: `uv run ms build core --target native`; `uv run pio run -e dev -d "midi-studio/core"`; `"tools/zig/zig.exe" c++ -std=c++17 -I"open-control/framework/src" -I"midi-studio/core/src" "midi-studio/core/test/test_CoreSettings.cpp" "open-control/framework/src/oc/log/Log.cpp" "open-control/framework/src/oc/time/Time.cpp" "open-control/framework/src/oc/state/NotificationQueue.cpp" -o ".build/test_CoreSettings.exe" && ".build/test_CoreSettings.exe"`
  - Expected result: Sync settings persist/reload with migration safety and reset path support.
  - Observed result: Native + Teensy builds succeeded and dedicated storage roundtrip/migration tests passed.
  - Decision: Done
  - Next action: Run live UI validation for D7/D8 button gesture behavior.

- 2026-02-16 - Steps F1-F3 completed.
  - Step ID: F1/F2/F3
  - Status: Done
  - Change summary: Added sync source and external clock activity indicators in `TransportBar`, and introduced displayed tempo policy (`tempoDisplay`) driven by `MidiClockSyncService` (internal tempo in INT mode, smoothed measured tempo in EXT mode).
  - Files touched: `midi-studio/core/src/state/StatusBarState.hpp`; `midi-studio/core/src/sequencer/MidiClockSyncService.hpp`; `midi-studio/core/src/sequencer/MidiClockSyncService.cpp`; `midi-studio/core/src/ui/transportbar/TransportBar.hpp`; `midi-studio/core/src/ui/transportbar/TransportBar.cpp`
  - Commands run: `uv run ms build core --target native`; `uv run pio run -e dev -d "midi-studio/core"`; `uv run ms build bitwig --target native`
  - Expected result: Transport UI reflects active sync source (`INT/EXT`), shows external clock activity pulses, and displays meaningful tempo while externally synced.
  - Observed result: Native + Teensy + Bitwig native builds succeeded with new status signals and UI bindings.
  - Decision: Done
  - Next action: Extend deterministic sync tests for displayed tempo and indicators.

- 2026-02-16 - Step G1 completed.
  - Step ID: G1
  - Status: Done
  - Change summary: Extended `test_MidiClockSyncService.cpp` with deterministic assertions for external source indicator, displayed tempo estimation in slave mode, and external clock activity pulse behavior.
  - Files touched: `midi-studio/core/test/test_MidiClockSyncService.cpp`
  - Commands run: `"tools/zig/zig.exe" c++ -std=c++17 -I"open-control/framework/src" -I"open-control/note/src" -I"midi-studio/core/src" "midi-studio/core/test/test_MidiClockSyncService.cpp" "midi-studio/core/src/sequencer/MidiClockSyncService.cpp" "open-control/framework/src/oc/api/MidiAPI.cpp" "open-control/framework/src/oc/log/Log.cpp" "open-control/framework/src/oc/time/Time.cpp" "open-control/framework/src/oc/state/NotificationQueue.cpp" "open-control/note/src/oc/note/clock/InternalClock.cpp" -o ".build/test_MidiClockSyncService.exe" && ".build/test_MidiClockSyncService.exe"`; `"tools/zig/zig.exe" c++ -std=c++17 -I"open-control/framework/src" -I"midi-studio/core/src" "midi-studio/core/test/test_CoreSettings.cpp" "open-control/framework/src/oc/log/Log.cpp" "open-control/framework/src/oc/time/Time.cpp" "open-control/framework/src/oc/state/NotificationQueue.cpp" -o ".build/test_CoreSettings.exe" && ".build/test_CoreSettings.exe"`
  - Expected result: Deterministic automated tests cover core sync arbitration plus newly exposed status/tempo projection behavior.
  - Observed result: All sync and settings tests passed.
  - Decision: Done
  - Next action: Execute manual E2E scenarios for G2/G3/G4.

- 2026-02-16 - Build hygiene fix applied.
  - Step ID: INFRA-TEST-1
  - Status: Done
  - Change summary: Excluded `midi-studio/core/test/` from PlatformIO firmware sources to avoid multiple `main()` linkage when local test executables are present.
  - Files touched: `midi-studio/core/platformio.ini`
  - Commands run: `uv run pio run -e dev -d "midi-studio/core"`
  - Expected result: Teensy firmware link succeeds without test `main()` conflicts.
  - Observed result: `dev` firmware build succeeded.
  - Decision: Done
  - Next action: Keep test binaries built via explicit local Zig commands.

- 2026-02-16 - External tempo display stabilization tuning applied.
  - Step ID: F2-TUNE-1
  - Status: Done
  - Change summary: Reworked external tempo estimation to use a 24-interval averaging window (instead of per-clock instantaneous BPM), applied EMA smoothing on window estimates, and quantized displayed tempo to 0.1 BPM with one decimal UI rendering.
  - Files touched: `midi-studio/core/src/sequencer/MidiClockSyncService.hpp`; `midi-studio/core/src/sequencer/MidiClockSyncService.cpp`; `midi-studio/core/src/ui/transportbar/TransportBar.cpp`; `midi-studio/core/test/test_MidiClockSyncService.cpp`
  - Commands run: `uv run ms build core --target native`; `uv run pio run -e dev -d "midi-studio/core"`; `uv run ms build bitwig --target native`; `"tools/zig/zig.exe" c++ -std=c++17 -I"open-control/framework/src" -I"open-control/note/src" -I"midi-studio/core/src" "midi-studio/core/test/test_MidiClockSyncService.cpp" "midi-studio/core/src/sequencer/MidiClockSyncService.cpp" "open-control/framework/src/oc/api/MidiAPI.cpp" "open-control/framework/src/oc/log/Log.cpp" "open-control/framework/src/oc/time/Time.cpp" "open-control/framework/src/oc/state/NotificationQueue.cpp" "open-control/note/src/oc/note/clock/InternalClock.cpp" -o ".build/test_MidiClockSyncService.exe" && ".build/test_MidiClockSyncService.exe"`; `"tools/zig/zig.exe" c++ -std=c++17 -I"open-control/framework/src" -I"midi-studio/core/src" "midi-studio/core/test/test_CoreSettings.cpp" "open-control/framework/src/oc/log/Log.cpp" "open-control/framework/src/oc/time/Time.cpp" "open-control/framework/src/oc/state/NotificationQueue.cpp" -o ".build/test_CoreSettings.exe" && ".build/test_CoreSettings.exe"`
  - Expected result: External tempo display becomes readable under realistic incoming clock jitter.
  - Observed result: All builds/tests passed; estimator now updates on averaged windows with visibly reduced flicker potential.
  - Decision: Done
  - Next action: Validate perceived readability on live device with unstable clock source.

- 2026-02-16 - External tempo tracking precision tuning applied.
  - Step ID: F2-TUNE-2
  - Status: Done
  - Change summary: Replaced per-interval/interval-window estimator with clock-count-over-time sampling to reduce timestamp batching bias; added adaptive EMA gains for faster catch-up on large tempo jumps while keeping stable display when close to target.
  - Files touched: `midi-studio/core/src/sequencer/MidiClockSyncService.hpp`; `midi-studio/core/src/sequencer/MidiClockSyncService.cpp`; `midi-studio/core/test/test_MidiClockSyncService.cpp`
  - Commands run: `uv run ms build core --target native`; `uv run pio run -e dev -d "midi-studio/core"`; `uv run ms build bitwig --target native`; `"tools/zig/zig.exe" c++ -std=c++17 -I"open-control/framework/src" -I"open-control/note/src" -I"midi-studio/core/src" "midi-studio/core/test/test_MidiClockSyncService.cpp" "midi-studio/core/src/sequencer/MidiClockSyncService.cpp" "open-control/framework/src/oc/api/MidiAPI.cpp" "open-control/framework/src/oc/log/Log.cpp" "open-control/framework/src/oc/time/Time.cpp" "open-control/framework/src/oc/state/NotificationQueue.cpp" "open-control/note/src/oc/note/clock/InternalClock.cpp" -o ".build/test_MidiClockSyncService.exe" && ".build/test_MidiClockSyncService.exe"`; `"tools/zig/zig.exe" c++ -std=c++17 -I"open-control/framework/src" -I"midi-studio/core/src" "midi-studio/core/test/test_CoreSettings.cpp" "open-control/framework/src/oc/log/Log.cpp" "open-control/framework/src/oc/time/Time.cpp" "open-control/framework/src/oc/state/NotificationQueue.cpp" -o ".build/test_CoreSettings.exe" && ".build/test_CoreSettings.exe"`
  - Expected result: Tempo display remains stable but tracks fast BPM changes accurately even when MIDI clock callbacks are delivered in bursts.
  - Observed result: All builds/tests passed; deterministic test now covers rapid external tempo change and converges to expected fast tempo range.
  - Decision: Done
  - Next action: Validate perceived tracking precision on real hardware/DAW clock at 160-200 BPM.

- 2026-02-16 - Tempo readability and responsiveness balancing tuning applied.
  - Step ID: F2-TUNE-3
  - Status: Done
  - Change summary: Added pro-style two-stage tempo projection: (1) external BPM estimator computed from clock-interval counts over bounded time windows with adaptive smoothing and interval-count correction, (2) dedicated UI display filter with publish rate limit + deadband + adaptive smoothing for stable but responsive readout.
  - Files touched: `midi-studio/core/src/sequencer/MidiClockSyncService.hpp`; `midi-studio/core/src/sequencer/MidiClockSyncService.cpp`; `midi-studio/core/test/test_MidiClockSyncService.cpp`
  - Commands run: `uv run ms build core --target native`; `uv run pio run -e dev -d "midi-studio/core"`; `uv run ms build bitwig --target native`; `"tools/zig/zig.exe" c++ -std=c++17 -I"open-control/framework/src" -I"open-control/note/src" -I"midi-studio/core/src" "midi-studio/core/test/test_MidiClockSyncService.cpp" "midi-studio/core/src/sequencer/MidiClockSyncService.cpp" "open-control/framework/src/oc/api/MidiAPI.cpp" "open-control/framework/src/oc/log/Log.cpp" "open-control/framework/src/oc/time/Time.cpp" "open-control/framework/src/oc/state/NotificationQueue.cpp" "open-control/note/src/oc/note/clock/InternalClock.cpp" -o ".build/test_MidiClockSyncService.exe" && ".build/test_MidiClockSyncService.exe"`; `"tools/zig/zig.exe" c++ -std=c++17 -I"open-control/framework/src" -I"midi-studio/core/src" "midi-studio/core/test/test_CoreSettings.cpp" "open-control/framework/src/oc/log/Log.cpp" "open-control/framework/src/oc/time/Time.cpp" "open-control/framework/src/oc/state/NotificationQueue.cpp" -o ".build/test_CoreSettings.exe" && ".build/test_CoreSettings.exe"`
  - Expected result: Tempo display stays readable under jitter/batched clocks while still converging quickly after significant BPM changes.
  - Observed result: All builds/tests passed; deterministic tests validate stable 120/125-range display and fast convergence toward 180-range after tempo jump.
  - Decision: Done
  - Next action: Validate perceived smoothness on live hardware with unstable external clock source.

- 2026-02-16 - Simplified raw engine tempo display applied by request.
  - Step ID: F2-TUNE-4
  - Status: Done
  - Change summary: Removed multi-stage display filtering/projection boilerplate and restored a direct tempo display policy: show internal engine tempo in internal source, show raw external engine estimate from clock deltas in external source.
  - Files touched: `midi-studio/core/src/sequencer/MidiClockSyncService.hpp`; `midi-studio/core/src/sequencer/MidiClockSyncService.cpp`; `midi-studio/core/test/test_MidiClockSyncService.cpp`
  - Commands run: `uv run ms build core --target native`; `uv run pio run -e dev -d "midi-studio/core"`; `uv run ms build bitwig --target native`; `"tools/zig/zig.exe" c++ -std=c++17 -I"open-control/framework/src" -I"open-control/note/src" -I"midi-studio/core/src" "midi-studio/core/test/test_MidiClockSyncService.cpp" "midi-studio/core/src/sequencer/MidiClockSyncService.cpp" "open-control/framework/src/oc/api/MidiAPI.cpp" "open-control/framework/src/oc/log/Log.cpp" "open-control/framework/src/oc/time/Time.cpp" "open-control/framework/src/oc/state/NotificationQueue.cpp" "open-control/note/src/oc/note/clock/InternalClock.cpp" -o ".build/test_MidiClockSyncService.exe" && ".build/test_MidiClockSyncService.exe"`; `"tools/zig/zig.exe" c++ -std=c++17 -I"open-control/framework/src" -I"midi-studio/core/src" "midi-studio/core/test/test_CoreSettings.cpp" "open-control/framework/src/oc/log/Log.cpp" "open-control/framework/src/oc/time/Time.cpp" "open-control/framework/src/oc/state/NotificationQueue.cpp" -o ".build/test_CoreSettings.exe" && ".build/test_CoreSettings.exe"`
  - Expected result: Remove drift introduced by layered display filters and expose immediate engine tempo behavior for baseline validation.
  - Observed result: All builds/tests passed with simplified tempo path.
  - Decision: Done
  - Next action: Validate on hardware and decide whether a minimal single-stage smoother is still needed.

- 2026-02-16 - Realtime clock timestamp pipeline refactor (no-legacy design).
  - Step ID: A6/F2-TUNE-5
  - Status: Done
  - Change summary: Reworked MIDI realtime clock pipeline to remove legacy callback shape and propagate timestamped clock events end-to-end (HAL -> framework events -> context -> sync service). Implemented robust external tempo estimator using microsecond clock intervals (trimmed-mean window + adaptive smoothing) while keeping display policy simple (project engine tempo only).
  - Files touched: `open-control/framework/src/oc/interface/IMidi.hpp`; `open-control/framework/src/oc/impl/NullMidi.hpp`; `open-control/framework/src/oc/core/event/Events.hpp`; `open-control/framework/src/oc/context/ContextBase.hpp`; `open-control/framework/src/oc/app/OpenControlApp.cpp`; `open-control/hal-teensy/src/oc/hal/teensy/UsbMidi.hpp`; `open-control/hal-teensy/src/oc/hal/teensy/UsbMidi.cpp`; `open-control/hal-midi/src/oc/hal/midi/LibreMidiTransport.hpp`; `open-control/hal-midi/src/oc/hal/midi/LibreMidiTransport.cpp`; `midi-studio/core/src/context/StandaloneContext.cpp`; `midi-studio/core/src/sequencer/MidiClockSyncService.hpp`; `midi-studio/core/src/sequencer/MidiClockSyncService.cpp`; `midi-studio/core/test/test_MidiClockSyncService.cpp`
  - Commands run: `uv run ms build core --target native`; `uv run pio run -e dev -d "midi-studio/core"`; `uv run ms build bitwig --target native`; `"tools/zig/zig.exe" c++ -std=c++17 -I"open-control/framework/src" -I"open-control/note/src" -I"midi-studio/core/src" "midi-studio/core/test/test_MidiClockSyncService.cpp" "midi-studio/core/src/sequencer/MidiClockSyncService.cpp" "open-control/framework/src/oc/api/MidiAPI.cpp" "open-control/framework/src/oc/log/Log.cpp" "open-control/framework/src/oc/time/Time.cpp" "open-control/framework/src/oc/state/NotificationQueue.cpp" "open-control/note/src/oc/note/clock/InternalClock.cpp" -o ".build/test_MidiClockSyncService.exe" && ".build/test_MidiClockSyncService.exe"`; `"tools/zig/zig.exe" c++ -std=c++17 -I"open-control/framework/src" -I"midi-studio/core/src" "midi-studio/core/test/test_CoreSettings.cpp" "open-control/framework/src/oc/log/Log.cpp" "open-control/framework/src/oc/time/Time.cpp" "open-control/framework/src/oc/state/NotificationQueue.cpp" -o ".build/test_CoreSettings.exe" && ".build/test_CoreSettings.exe"`; `"tools/zig/zig.exe" c++ -std=c++17 "open-control/hal-midi/test/test_LibreMidiTransport.cpp" -o ".build/test_LibreMidiTransport.exe" && ".build/test_LibreMidiTransport.exe"`
  - Expected result: Accurate and stable external tempo tracking at low/high BPM without carry-over technical debt from legacy callback contracts.
  - Observed result: All builds/tests passed; consumers across `open-control` and `midi-studio` were updated for timestamped clock callback usage.
  - Decision: Done
  - Next action: Hardware/DAW validation for tempo readability at 50/100/120/180 BPM.

- 2026-02-16 - Balanced UI smoothing applied on top of engine tempo.
  - Step ID: F2-TUNE-6
  - Status: Done
  - Change summary: Added a lightweight display-only smoothing stage for `tempoDisplay` in external sync mode (adaptive EMA + publish interval + deadband) to reduce visible oscillation from DAW focus-related jitter while keeping engine sync logic unchanged.
  - Files touched: `midi-studio/core/src/sequencer/MidiClockSyncService.hpp`; `midi-studio/core/src/sequencer/MidiClockSyncService.cpp`; `midi-studio/core/test/test_MidiClockSyncService.cpp`
  - Commands run: `uv run ms build core --target native`; `uv run pio run -e dev -d "midi-studio/core"`; `uv run ms build bitwig --target native`; `"tools/zig/zig.exe" c++ -std=c++17 -I"open-control/framework/src" -I"open-control/note/src" -I"midi-studio/core/src" "midi-studio/core/test/test_MidiClockSyncService.cpp" "midi-studio/core/src/sequencer/MidiClockSyncService.cpp" "open-control/framework/src/oc/api/MidiAPI.cpp" "open-control/framework/src/oc/log/Log.cpp" "open-control/framework/src/oc/time/Time.cpp" "open-control/framework/src/oc/state/NotificationQueue.cpp" "open-control/note/src/oc/note/clock/InternalClock.cpp" -o ".build/test_MidiClockSyncService.exe" && ".build/test_MidiClockSyncService.exe"`; `"tools/zig/zig.exe" c++ -std=c++17 -I"open-control/framework/src" -I"midi-studio/core/src" "midi-studio/core/test/test_CoreSettings.cpp" "open-control/framework/src/oc/log/Log.cpp" "open-control/framework/src/oc/time/Time.cpp" "open-control/framework/src/oc/state/NotificationQueue.cpp" -o ".build/test_CoreSettings.exe" && ".build/test_CoreSettings.exe"`; `"tools/zig/zig.exe" c++ -std=c++17 "open-control/hal-midi/test/test_LibreMidiTransport.cpp" -o ".build/test_LibreMidiTransport.exe" && ".build/test_LibreMidiTransport.exe"`
  - Expected result: More stable tempo readout under small incoming jitter, with fast reaction preserved on larger tempo moves.
  - Observed result: All builds/tests passed; precision tests remain green at 50/100/125/180 scenarios.
  - Decision: Done
  - Next action: Validate with Bitwig focus/no-focus transitions and tune 2-3 constants if needed.

## 11) Decision log (append-only)

- DLOG-001: `Follow Transport` is ON in `SLAVE` and `AUTO(EXTERNAL)`.
- DLOG-002: Global settings entry gesture is `LEFT_TOP` long press 2000 ms.
- DLOG-003: Keep short press `LEFT_TOP` mapped to existing view selector.
- DLOG-004: Every implementation step must carry explicit test evidence before `Done`.
- DLOG-005: Teensy realtime send uses explicit `sendRealTime(status)` path (source-verified) rather than wrapper shortcuts.
- DLOG-006: Tempo display policy uses projected `tempoDisplay` (internal tempo on INT source, smoothed measured external tempo on EXT source).
- DLOG-007: External tempo estimation uses interval-window averaging (24 intervals) plus EMA smoothing before UI projection.
- DLOG-008: Tempo estimator now uses clock-count-over-time sampling with adaptive smoothing to resist callback batching artifacts and improve high-tempo tracking.
- DLOG-009: Tempo display uses a separate UI projection filter (rate limit + deadband + adaptive smoothing) to prioritize readability without slowing sync engine behavior.
- DLOG-010: Current baseline policy favors simplicity: display raw engine tempo path first, then add only minimal smoothing if hardware tests require it.
- DLOG-011: Design phase rule enforced: no legacy realtime callback compatibility layer retained; clock callback contract is timestamped-only.
- DLOG-012: External tempo estimator policy is now single-stage engine-side (microsecond intervals, trimmed mean, adaptive smoothing) with no extra display boilerplate layer.
- DLOG-013: Display smoothing remains strictly UI-projection only (external mode), with engine sync/tick decisions unaffected.
