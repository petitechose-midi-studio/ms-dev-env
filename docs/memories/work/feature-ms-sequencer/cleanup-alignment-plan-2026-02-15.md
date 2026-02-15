# Cleanup Plan - Sequencer Core (2026-02-15)

## Goal

Clean up sequencer handlers/UI code in `midi-studio/core` for long-term maintainability,
while keeping behavior aligned with `plugin-bitwig` input patterns (scope/latch/discrete
encoder logic) and avoiding over-engineering.

## Ordered execution plan

1. **Page/index safety first**
   - Normalize page before computing absolute step index.
   - Apply in:
     - `src/handler/sequencer/SequencerMacroPropertyHandler.cpp`
     - `src/context/StandaloneContext.cpp` (`syncSequencerMacroEncoderPositions`)
   - Target: remove any potential `uint8_t` wrap-around path.

2. **Wrap utility standardization**
   - Replace local `wrapIndex` implementations with `oc::util::wrapIndex`.
   - Apply in:
     - `src/handler/sequencer/SequencerStepHandler.cpp`
     - `src/handler/sequencer/SequencerPropertySelectorHandler.cpp`

3. **Shared MIDI note-name formatter**
   - Remove duplicated `formatNoteName` code.
   - Move to shared utility in `core/src/midi` and reuse from:
     - `src/ui/view/SequencerView.cpp`
     - `src/context/StandaloneContext.cpp` (step edit overlay render)

4. **Small sequencer input helpers (no heavy abstraction)**
   - Add minimal shared helpers for normalized conversion to reduce repeated clamp/
     rounding logic:
     - NOTE/VEL: `0..127`
     - GATE: `0..100`
     - index/position conversion for discrete rows
   - Apply in:
     - `src/handler/sequencer/SequencerStepEditHandler.cpp`
     - `src/handler/sequencer/SequencerMacroPropertyHandler.cpp`
     - `src/handler/sequencer/SequencerPatternConfigHandler.cpp`

5. **Validation after each step**
   - Run: `pio run -t upload`
   - Keep failures visible in log/report.

6. **Final review pass**
   - Re-read all modified files fully (not partial slices).
   - Do a final cosmetic cleanup pass (naming/comments/consistency only, no behavior change).

## Non-goals (explicit)

- No architectural split of sequencer UI into `midi-studio/ui` at this stage.
- No broad refactor outside touched files.
- No behavior redesign; only safe cleanup + parity-oriented consistency.
