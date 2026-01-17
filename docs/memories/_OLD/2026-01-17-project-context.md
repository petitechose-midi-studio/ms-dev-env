# Project Context for AI Agents - MIDI Studio & OpenControl

_This file contains critical rules and patterns that AI agents must follow when implementing code in this project. Focus on unobvious details that agents might otherwise miss._

**Project:** petitechose-audio (MIDI Studio + OpenControl)
**Owner:** miu-lab
**Last Updated:** 2026-01-07

---

## 1. Project Overview

### What This Project Is

| Component | Purpose | License |
|-----------|---------|---------|
| **MidiStudio** | Commercial hardware MIDI controller product | CC-BY-NC-SA 4.0 |
| **OpenControl** | Reusable embedded framework for MIDI controllers | Apache 2.0 |
| **oc-bridge** | Serial-to-UDP bridge (Rust) | MIT |

### Directory Structure

```
petitechose-audio/
├── midi-studio/
│   ├── core/               # Standalone MIDI controller firmware (8 macros)
│   ├── plugin-bitwig/      # Bitwig DAW integration (C++ + Java)
│   └── hardware/           # PCB + CNC designs (KiCad, OnShape)
├── open-control/
│   ├── framework/          # Core framework (Signal, Context, Bindings)
│   ├── framework.wiki/     # Framework API documentation (19 MD files)
│   ├── hal-teensy/         # Teensy 4.1 HAL implementation
│   ├── hal-common/         # Shared HAL types
│   ├── ui-lvgl/            # LVGL integration
│   ├── ui-lvgl-components/ # Custom LVGL widgets
│   ├── bridge/             # oc-bridge (Rust)
│   ├── protocol-codegen/   # Python → C++/Java code generator
│   ├── cli-tools/          # CLI utilities
│   └── example-*/          # Example projects (6 total)
├── _bmad/                  # BMAD methodology files
├── _bmad-output/           # Generated BMAD artifacts
└── .serena/memories/       # Project memory files
```

---

## 2. Technology Stack

### Hardware Target
- **MCU:** Teensy 4.1 (ARM Cortex-M7 @ 450 MHz, underclocked from 600 MHz)
- **RAM:** 8 MB PSRAM (MANDATORY - soldered on Teensy underside)
- **Display:** ILI9341 2.8" TFT (320×240, SPI @ 20 MHz)
- **Encoders:** 10 total (8 smooth Bourns + 1 detented + 1 optical 600 PPR)
- **Buttons:** 15 total (via CD74HC4067 16-ch multiplexer)
- **Power:** USB-powered only (~250 mA max)

### Software Stack
- **Language:** C++17 (firmware), Java 21 (Bitwig extension), Python 3.13+ (codegen)
- **UI Framework:** LVGL 9.4.0+
- **Build System:** PlatformIO (firmware), Maven (Java)
- **Protocol:** COBS-framed Binary (8-bit), UDP to Bitwig

### Key Dependencies (Transitive via library.json)
```
hal-teensy/library.json:
  - luni64/EncoderTool@^3.2.0
  - vindar/ILI9341_T4@^1.6.0  # Note: Capital T4

ui-lvgl/library.json:
  - lvgl/lvgl@^9.4.0
```

---

## 3. Documentation Reference

### MANDATORY READING Before Implementation

| Task | Read First | File Path |
|------|------------|-----------|
| Any code change | `INVARIANTS.md` | `midi-studio/core/docs/INVARIANTS.md` |
| Adding a Handler | `HOW_TO_ADD_HANDLER.md` | `midi-studio/core/docs/HOW_TO_ADD_HANDLER.md` |
| Adding an Overlay | `HOW_TO_ADD_OVERLAY.md` | `midi-studio/core/docs/HOW_TO_ADD_OVERLAY.md` |
| Adding a View | `HOW_TO_ADD_VIEW.md` | `midi-studio/core/docs/HOW_TO_ADD_VIEW.md` |
| Adding a Widget | `HOW_TO_ADD_WIDGET.md` | `midi-studio/core/docs/HOW_TO_ADD_WIDGET.md` |
| State management | `STATE_MANAGEMENT.md` | `midi-studio/core/docs/STATE_MANAGEMENT.md` |
| Code style | `CODE_STYLE.md` | `midi-studio/core/docs/CODE_STYLE.md` |
| Framework API | `README.md` | `open-control/framework/README.md` |

### Framework API Documentation (Wiki)
Located in `open-control/framework.wiki/`:
- `API-Signal.md` - Signal<T> reactive state
- `API-DerivedSignal.md` - Computed signals
- `API-SignalWatcher.md` - Multi-signal coalescing
- `API-Input-Binding.md` - Button/Encoder fluent API
- `API-Encoder.md` - Encoder modes and configuration
- `API-Context.md` - Application lifecycle
- `API-Settings.md` - Persistent configuration
- `API-AutoPersist.md` - Debounced persistence
- `API-Result.md` - Error handling

---

## 4. Architecture Principles

### Single Source of Truth
```
State (Signals) = CANONICAL
UI (LVGL)       = PROJECTION of state
```
**NEVER** store state in UI widgets. Always read from Signals.

### Reactive Flow Pattern
```
User Input → Handler → State (Signal::set) → Subscription → View Update
                ↓
           Protocol (MIDI/Serial)
```

### Three-Layer Separation

| Layer | Responsibilities | Forbidden |
|-------|-----------------|-----------|
| **InputHandlers** | State changes + Protocol messages | LVGL calls |
| **HostHandlers** | State changes only | Protocol + LVGL |
| **Views** | LVGL rendering + Subscriptions | Protocol + State mutation |

**Reference:** `midi-studio/core/docs/INVARIANTS.md` Section 3

---

## 5. Critical Implementation Rules

### 5.1 Input Authority (MUST FOLLOW)

Only ONE scope has input authority at any time:
```
Priority: Overlays (1) > Views (2) > Global (3)
```

When overlay opens:
1. Update state (e.g., `overlay.visible.set(true)`)
2. Clear scope bindings (buttons/encoders)
3. Release any latches

```cpp
// CORRECT
void openOverlay() {
    state_.macroEdit.visible.set(true);
    buttons().clearScope(previousScope);
    buttons().clearLatch(buttonId);
}
```

**Reference:** `midi-studio/core/docs/INVARIANTS.md` Section 2, 4, 5

### 5.2 Signal Usage

```cpp
// ALWAYS use set() to trigger subscriptions
signal.set(newValue);  // CORRECT

// NEVER modify internal state directly
signal.get() = newValue;  // WRONG - no notification
```

**Reference:** `open-control/framework.wiki/API-Signal.md`

### 5.3 Subscription Lifetime (RAII)

```cpp
class MyView {
    Subscription sub_;  // Member variable - auto-unsubscribes on destruction

    void init() {
        sub_ = state_.value.subscribe([this](float v) {
            updateUI(v);
        });
    }
};
```

**Reference:** `midi-studio/core/docs/STATE_MANAGEMENT.md` Section 4

### 5.4 Echo Suppression (80ms Window)

When controller sends value to host, host echoes it back. Suppress echoes:

```java
// BitwigConfig.java
public static final int ECHO_TIMEOUT_MS = 80;

// DeviceController.java
public boolean consumeEcho(int paramIndex) {
    long elapsed = System.currentTimeMillis() - lastControllerChangeTime[paramIndex];
    return elapsed < ECHO_TIMEOUT_MS;
}
```

**Reference:** `midi-studio/core/docs/INVARIANTS.md` Section 6

### 5.5 No Global Redraws

```cpp
// WRONG - invalidates entire screen
lv_obj_invalidate(lv_scr_act());

// CORRECT - invalidate only what changed
lv_obj_invalidate(specific_widget);
// Or better: let LVGL handle via dirty flags
```

**Reference:** `midi-studio/core/docs/INVARIANTS.md` Section 9

### 5.6 Memory Constraints

```cpp
// PREFER fixed-size containers
std::array<float, 8> values;  // GOOD

// AVOID dynamic allocation in hot paths
std::vector<float> values;    // BAD in update()
new SomeClass();              // BAD in update()
```

**Reference:** `midi-studio/core/docs/CODE_STYLE.md` Section "Embedded Specifics"

---

## 6. Key Patterns

### 6.1 Fluent Input Binding

**Read before implementing:** `midi-studio/core/docs/HOW_TO_ADD_HANDLER.md`
**API Reference:** `open-control/framework.wiki/API-Input-Binding.md`

```cpp
// Button binding
onButton(BTN_PLAY)
    .press()
    .scope(viewScope)
    .then([this]{ handlePlay(); });

// Encoder binding with condition
onEncoder(ENC_VOLUME)
    .turn()
    .scope(viewScope)
    .when([this]{ return !overlayVisible(); })
    .then([this](float v){ setVolume(v); });

// Long press
onButton(BTN_SHIFT)
    .longPress(500)
    .then([this]{ showMenu(); });
```

**Implementation files:**
- `open-control/framework/src/oc/core/input/ButtonBuilder.hpp`
- `open-control/framework/src/oc/core/input/EncoderBuilder.hpp`

### 6.2 DerivedSignal (Auto-computed Values)

**API Reference:** `open-control/framework.wiki/API-DerivedSignal.md`

```cpp
// Value signal
Signal<float> value{0.5f};

// Display value auto-updates when value changes
DerivedStringSignal<float, 8> displayValue{value,
    [](float v, char* buf, size_t size) {
        uint8_t cc = static_cast<uint8_t>(v * 127.0f);
        std::snprintf(buf, size, "%d", cc);
    }
};
```

**Implementation file:** `open-control/framework/src/oc/state/DerivedSignal.hpp`

### 6.3 SignalWatcher (Multi-signal Coalescing)

**API Reference:** `open-control/framework.wiki/API-SignalWatcher.md`

```cpp
SignalWatcher watcher_;

void setup() {
    watcher_.watchAll(
        [this]() { render(); },  // Called once even if multiple signals change
        state_.visible,
        state_.channel,
        state_.cc
    );
}
```

**Implementation file:** `open-control/framework/src/oc/state/SignalWatcher.hpp`

### 6.4 Props-Based Overlay Rendering

**Read before implementing:** `midi-studio/core/docs/HOW_TO_ADD_OVERLAY.md`

```cpp
// Overlay is STATELESS - receives props
struct MacroEditOverlayProps {
    uint8_t editingIndex;
    uint8_t channel;
    uint8_t cc;
    uint8_t focusedRow;
    bool visible;
};

class MacroEditOverlay {
    void render(const MacroEditOverlayProps& props);  // Pure function
};

// Context owns state and calls render
void Context::renderMacroEdit() {
    overlay_->render({
        .editingIndex = state_.macroEdit.editingIndex.get(),
        .channel = state_.macroEdit.tempChannel.get(),
        // ...
    });
}
```

**Implementation file:** `midi-studio/core/src/ui/macro/MacroEditOverlay.hpp`

### 6.5 ExclusiveVisibilityStack

**Implementation file:** `open-control/framework/src/oc/state/ExclusiveVisibilityStack.hpp`

```cpp
ExclusiveVisibilityStack<OverlayType> overlays_;

// Only ONE overlay visible at a time
overlays_.show(OverlayType::MACRO_EDIT);  // Hides any other
overlays_.hide(OverlayType::MACRO_EDIT);
```

### 6.6 AutoPersist with Debounce

**API Reference:** `open-control/framework.wiki/API-AutoPersist.md`

```cpp
AutoPersist<MySettings> persist_(settings_, 1000);  // 1s debounce

void setup() {
    persist_.watch(volumeSignal, [](MySettings& s, float v) {
        s.volume = v;
    });
}

void loop() {
    persist_.update();  // Saves after 1s of no changes
}
```

**Implementation file:** `open-control/framework/src/oc/state/AutoPersist.hpp`

---

## 7. Protocol Architecture (Bitwig Plugin)

### Communication Flow
```
Teensy (C++) ←USB Serial + COBS→ oc-bridge (Rust) ←UDP:9000→ Bitwig (Java)
```

### Message Directions

| Direction | Example Messages |
|-----------|-----------------|
| Controller → Host | `REMOTE_CONTROL_VALUE`, `DEVICE_SELECT`, `TRANSPORT_PLAY` |
| Host → Controller | `DEVICE_REMOTE_CONTROLS_BATCH`, `TRANSPORT_PLAYING_STATE` |

### Batch Updates Structure (50Hz)
```cpp
// DeviceRemoteControlsBatchMessage (actual structure)
struct DeviceRemoteControlsBatchMessage {
    uint8_t sequenceNumber;          // Sequence for ordering
    uint8_t dirtyMask;               // Which params changed
    uint8_t echoMask;                // Which are echoes
    uint8_t hasAutomationMask;       // Which have automation
    std::array<float, 8> values;     // NORM8 encoded
    std::array<float, 8> modulatedValues;
    std::array<std::string, 8> displayValues;
};
```

### Protocol Generation
```bash
# Regenerate protocol from Python definitions
cd midi-studio/plugin-bitwig
./script/protocol/generate_protocol.sh
```

Files generated:
- `src/protocol/struct/*.hpp` (C++)
- `host/src/protocol/struct/*.java` (Java)
- `MessageID.hpp/.java`, `ProtocolCallbacks.*`, `DecoderRegistry.*`

**Protocol definitions:** `midi-studio/plugin-bitwig/protocol/message/`

---

## 8. File Naming & Code Style

**Reference:** `midi-studio/core/docs/CODE_STYLE.md`

### Naming Conventions
- **Classes:** `PascalCase` (e.g., `MacroValueHandler`)
- **Methods:** `camelCase` (e.g., `handleValueChange`)
- **Constants:** `SCREAMING_SNAKE_CASE` (e.g., `MAX_MACROS`)
- **Private members:** `snake_case_` trailing underscore (e.g., `event_bus_`)
- **Files:** `PascalCase.hpp/.cpp` matching class name

### Include Order (6 Groups)
```cpp
// 1. Paired header
#include "ThisFile.hpp"

// 2. C headers
#include <cstdint>

// 3. C++ STL
#include <array>
#include <functional>

// 4. External libraries
#include <lvgl.h>

// 5. Project headers (framework)
#include <oc/state/Signal.hpp>

// 6. Project headers (local)
#include "state/CoreState.hpp"
```

### Indentation
- **4 spaces** (not tabs)
- **K&R braces** (opening brace on same line)
- **~100 char lines**

---

## 9. Testing

### Unit Tests (Framework)
```bash
cd open-control/framework
pio test -e native
# 224 tests
```

### Integration Testing
- MacroEditOverlay lifecycle (open/edit/save/cancel)
- Latch behavior (acquire/release)
- Echo suppression timing

---

## 10. Common Pitfalls to Avoid

**Reference:** `midi-studio/core/docs/INVARIANTS.md` (full document)

### Pitfall 1: Modifying State in Views
```cpp
// WRONG - View should not modify state
void MacroView::onClick() {
    state_.value.set(0.5f);  // NO!
}

// CORRECT - Handler modifies state, View only displays
void MacroValueHandler::handleClick() {
    state_.value.set(0.5f);  // YES
}
```

### Pitfall 2: Forgetting Scope Cleanup
```cpp
// WRONG - Bindings leak when overlay closes
void closeOverlay() {
    state_.visible.set(false);
}

// CORRECT - Clear scope before closing
void closeOverlay() {
    buttons().clearScope(overlayScope);
    buttons().clearLatch(triggerButton);
    state_.visible.set(false);
}
```

### Pitfall 3: Using std::string in Embedded
```cpp
// WRONG - heap allocation
std::string label = "Macro 1";

// CORRECT - fixed buffer
SignalLabel label;  // 32 chars max, stack allocated
label.set("Macro 1");
```

**SignalLabel defined in:** `open-control/framework/src/oc/state/SignalString.hpp`

### Pitfall 4: Blocking in Callbacks
```cpp
// WRONG - blocks main loop
signal.subscribe([](float v) {
    delay(100);  // NO!
    sendHttp(...);  // NO!
});

// CORRECT - quick state update only
signal.subscribe([this](float v) {
    dirty_ = true;  // Set flag, process later
});
```

### Pitfall 5: Direct LVGL Manipulation in Handlers
```cpp
// WRONG - Handler touches LVGL
void MacroValueHandler::handle(float v) {
    lv_label_set_text(label_, "...");  // NO!
}

// CORRECT - Handler updates state, View subscribes
void MacroValueHandler::handle(float v) {
    state_.displayValue.set(formatValue(v));  // YES
}
```

### Pitfall 6: Missing Loop Variable Capture
```cpp
// WRONG - captures by reference, undefined behavior
for (uint8_t i = 0; i < COUNT; ++i) {
    subs_.push_back(signal.subscribe([this, &i](float v) { ... }));
    //                                       ^^^ WRONG!
}

// CORRECT - capture by value
for (uint8_t i = 0; i < COUNT; ++i) {
    subs_.push_back(signal.subscribe([this, i](float v) { ... }));
    //                                      ^ by value
}
```

---

## 11. Key Files Reference

### Core Architecture
| File | Purpose |
|------|---------|
| `midi-studio/core/docs/INVARIANTS.md` | Non-negotiable rules |
| `midi-studio/core/docs/CODE_STYLE.md` | Coding conventions |
| `midi-studio/core/docs/ARCHITECTURE_REVIEW.md` | System assessment |
| `midi-studio/core/docs/STATE_MANAGEMENT.md` | Signal usage patterns |
| `midi-studio/core/docs/EXTENSION_CHECKLIST.md` | Pre-commit checklist |
| `open-control/framework/README.md` | Framework API overview |

### HOW-TO Guides
| File | Purpose |
|------|---------|
| `midi-studio/core/docs/HOW_TO_ADD_HANDLER.md` | Input handling |
| `midi-studio/core/docs/HOW_TO_ADD_OVERLAY.md` | Modal overlays |
| `midi-studio/core/docs/HOW_TO_ADD_VIEW.md` | Full-screen views |
| `midi-studio/core/docs/HOW_TO_ADD_WIDGET.md` | UI components |

### State Management
| File | Purpose |
|------|---------|
| `open-control/framework/src/oc/state/Signal.hpp` | Reactive state |
| `open-control/framework/src/oc/state/DerivedSignal.hpp` | Computed state |
| `open-control/framework/src/oc/state/SignalString.hpp` | SignalLabel, SignalTiny |
| `open-control/framework/src/oc/state/SignalWatcher.hpp` | Multi-signal coalescing |
| `open-control/framework/src/oc/state/Settings.hpp` | Persistence |
| `midi-studio/core/src/state/CoreState.hpp` | Application state |

### Input System
| File | Purpose |
|------|---------|
| `open-control/framework/src/oc/core/input/InputBinding.hpp` | Binding registry |
| `open-control/framework/src/oc/core/input/ButtonBuilder.hpp` | Button fluent API |
| `open-control/framework/src/oc/core/input/EncoderBuilder.hpp` | Encoder fluent API |
| `open-control/framework/src/oc/api/ButtonAPI.hpp` | Button API |
| `open-control/framework/src/oc/api/EncoderAPI.hpp` | Encoder API |

### UI System
| File | Purpose |
|------|---------|
| `midi-studio/core/src/ui/widget/MacroKnobWidget.hpp` | Main widget |
| `midi-studio/core/src/ui/macro/MacroEditOverlay.hpp` | Overlay example |
| `midi-studio/core/src/context/StandaloneContext.hpp` | Main context |

### Protocol (Bitwig)
| File | Purpose |
|------|---------|
| `midi-studio/plugin-bitwig/protocol/` | Message definitions (Python) |
| `midi-studio/plugin-bitwig/src/protocol/BitwigProtocol.hpp` | C++ protocol |
| `midi-studio/plugin-bitwig/host/src/protocol/Protocol.java` | Java protocol |

---

## 12. Serena Memories Available

These files contain additional context:
- `changelog` - Version history
- `code-style` - Style guidelines
- `project-paths` - Path reference
- `quality-cleanup-master-plan` - Refactoring roadmap
- `refactor-core-architecture-plan` - Architecture improvements
- `refactor-handlers-plan` - Handler reorganization
- `refactor-widgets-plan` - Widget improvements

Use `mcp__serena__read_memory` to access these.

---

## 13. Quick Commands

### Build & Upload Firmware
```bash
cd midi-studio/core  # or plugin-bitwig
pio run -e dev       # Build
pio run -e dev -t upload  # Upload
```

### Build Bitwig Extension
```bash
cd midi-studio/plugin-bitwig/host
mvn package
# Output: target/midi_studio.bwextension
```

### Run oc-bridge
```bash
cd open-control/bridge
cargo run --release
```

### Generate Protocol
```bash
cd midi-studio/plugin-bitwig
./script/protocol/generate_protocol.sh
```

---

## 14. When Adding New Features

### Checklist (from EXTENSION_CHECKLIST.md)
1. [ ] Read `INVARIANTS.md` first
2. [ ] Read the relevant `HOW_TO_ADD_*.md` guide
3. [ ] Identify which layer (Handler/State/View)
4. [ ] Define Signals for new state
5. [ ] Create Handler for input processing
6. [ ] Create/update View for UI
7. [ ] Add scoped bindings with cleanup
8. [ ] Test overlay lifecycle if applicable
9. [ ] Run unit tests
10. [ ] Check memory usage (no new heap in hot paths)

### Questions to Ask
- Does this state belong in CoreState or a new struct?
- Who owns this binding's scope?
- What happens when overlay closes?
- Is echo suppression needed for this protocol message?

---

_This document should be updated when significant architectural changes are made._
