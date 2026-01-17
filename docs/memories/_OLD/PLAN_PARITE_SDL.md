# Plan de parité Teensy / Native / WASM

## Objectif
Permettre à `core` et `plugin-bitwig` de compiler et fonctionner sur:
- Teensy 4.1 (existant)
- Native SDL (Windows/Linux/macOS)
- WASM SDL (navigateur)

## Architecture cible

```
┌─────────────────────────────────────────────────────────────────────────┐
│                            midi-studio                                   │
├─────────────────────────────────┬───────────────────────────────────────┤
│            core/                │           plugin-bitwig/              │
│  src/                           │  src/                                 │
│    app/AppLogic.hpp             │    app/AppLogic.hpp    [À CRÉER]      │
│      → registerContexts()       │      → registerContexts()             │
│    state/CoreState.hpp          │    state/BitwigState.hpp (interne)    │
│    context/StandaloneContext    │    context/BitwigContext              │
│                                 │                                       │
│  main.cpp (Teensy)              │  main.cpp (Teensy)                    │
│  sdl/main-native.cpp            │  sdl/main-native.cpp   [À CRÉER]      │
│  sdl/main-wasm.cpp              │  sdl/main-wasm.cpp     [À CRÉER]      │
├─────────────────────────────────┴───────────────────────────────────────┤
│                        core/sdl/ (partagé)                              │
│  SdlRunner.hpp/cpp  → Setup SDL/LVGL/HwSimulator                        │
│  HwSimulator.hpp/cpp                                                    │
│  MemoryStorage.hpp/cpp                                                  │
│  HwLayout.hpp                                                           │
│  CMakeLists.txt     → Build SDL (réutilisé par plugin-bitwig)           │
└─────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────┐
│                          open-control                                    │
├─────────────────────────────────────────────────────────────────────────┤
│  hal-sdl/      → AppBuilder SDL, InputMapper, SdlBridge                 │
│  hal-midi/     → LibreMidiTransport (Native + WASM via libremidi)       │
│  hal-net/      → UdpTransport (Native), WebSocketTransport (WASM)       │
│  framework/    → OpenControlApp, IContext, IMessageTransport            │
└─────────────────────────────────────────────────────────────────────────┘
```

## Transports par plateforme

```
Teensy   → USB Serial (COBS)  → oc-bridge → UDP:9000 → Extension Bitwig
Native   → UDP:9001           → oc-bridge → UDP:9000 → Extension Bitwig  
WASM     → WebSocket:9002     → oc-bridge → UDP:9000 → Extension Bitwig
```

---

## Phase 1: Rendre BitwigContext portable ✅ FAIT

### 1.1 Config générateur de fonts ✅
- [x] `plugin-bitwig/script/lvgl/icon/icon_converter.conf`
  - Ajouté `PLATFORM_INCLUDE='"config/PlatformCompat.hpp"'`

### 1.2 Fonts régénérées ✅
- [x] `src/ui/font/data/bitwig_icons_*.hpp` et `.c.inc`
  - Maintenant utilisent `#include "config/PlatformCompat.hpp"`

### 1.3 BitwigBootContext.hpp ✅
- [x] `#include <Arduino.h>` → `#include <oc/time/Time.hpp>`
- [x] `millis()` → `oc::time::millis()`

---

## Phase 2: Factoriser registerContexts()

### 2.1 Uniformiser core/main.cpp (Teensy)

**Fichier:** `core/main.cpp`

**Avant (inline):**
```cpp
app->registerContextWithFactory(
    Config::ContextID::STANDALONE,
    "Standalone",
    [&]() { return std::make_unique<core::context::StandaloneContext>(*coreState); });
```

**Après:**
```cpp
#include "app/AppLogic.hpp"
// ...
core::app::registerContexts(*app, *coreState);
```

### 2.2 Créer bitwig::app::registerContexts()

**Fichier à créer:** `plugin-bitwig/src/app/AppLogic.hpp`

```cpp
#pragma once

#include <oc/app/OpenControlApp.hpp>
#include "context/BitwigBootContext.hpp"
#include "context/BitwigContext.hpp"

namespace bitwig {

enum class ContextID : uint8_t {
    BOOT = 0,
    BITWIG = 1,
};

namespace app {

inline void registerContexts(oc::app::OpenControlApp& app) {
    app.registerContext<BitwigBootContext>(ContextID::BOOT, "Boot");
    app.registerContext<BitwigContext>(ContextID::BITWIG, "Bitwig");
}

} // namespace app
} // namespace bitwig
```

### 2.3 Mettre à jour plugin-bitwig/main.cpp (Teensy)

**Avant:**
```cpp
app->registerContext<bitwig::BitwigBootContext>(BitwigContextID::BOOT, "Boot");
app->registerContext<bitwig::BitwigContext>(BitwigContextID::BITWIG, "Bitwig");
```

**Après:**
```cpp
#include "app/AppLogic.hpp"
// ...
bitwig::app::registerContexts(*app);
```

---

## Phase 3: Refactorer SdlRunner

### 3.1 Responsabilités de SdlRunner

**FAIT par SdlRunner:**
- SDL_Init
- LVGL SdlBridge
- HwSimulator
- InputMapper + keyboard mappings
- Expose `appBuilder()` pré-configuré

**NE FAIT PAS (responsabilité de main):**
- Création de Storage/State
- Configuration MIDI transport
- Configuration remote transport
- registerContexts()
- app.begin()

### 3.2 Nouvelle interface SdlRunner

**Fichier:** `core/sdl/SdlRunner.hpp`

```cpp
class SdlRunner {
public:
    SdlRunner();
    ~SdlRunner();

    /// Setup SDL, LVGL, HwSimulator, InputMapper
    bool init(int argc, char** argv);

    /// Get pre-configured AppBuilder (controllers + inputConfig)
    /// Caller adds .midi() and optionally .remote(), then converts to app
    oc::hal::sdl::AppBuilder appBuilder();

    /// Main loop iteration (events, LVGL refresh)
    /// Returns false if quit requested
    bool tick(oc::app::OpenControlApp& app);

    /// Cleanup
    void shutdown();

    /// Access for state update in tick
    void updateState(std::function<void()> stateUpdate);

private:
    std::unique_ptr<oc::ui::lvgl::SdlBridge> bridge_;
    std::unique_ptr<oc::hal::sdl::InputMapper> input_;
    std::unique_ptr<desktop::HwSimulator> hwSim_;
    SDL_Renderer* renderer_ = nullptr;
    bool running_ = false;
};
```

### 3.3 Nouveau main-native.cpp pour core

**Fichier:** `core/sdl/main-native.cpp`

```cpp
#include "SdlRunner.hpp"
#include "MemoryStorage.hpp"
#include "app/AppLogic.hpp"
#include "state/CoreState.hpp"
#include <oc/hal/midi/LibreMidiTransport.hpp>

int main(int argc, char** argv) {
    SdlRunner runner;
    if (!runner.init(argc, argv)) return 1;

    // State (survit aux context switches)
    desktop::MemoryStorage storage;
    core::state::CoreState coreState(storage);

    // App avec MIDI
    auto app = runner.appBuilder()
        .midi(std::make_unique<oc::hal::midi::LibreMidiTransport>(
            oc::hal::midi::LibreMidiConfig{.appName = "MIDI Studio"}));

    // Contextes
    core::app::registerContexts(app, coreState);
    app.begin();

    // Main loop
    while (runner.tick(app)) {
        coreState.update();
    }

    runner.shutdown();
    return 0;
}
```

---

## Phase 4: Créer build SDL pour plugin-bitwig

### 4.1 Créer main-native.cpp pour plugin-bitwig

**Fichier à créer:** `plugin-bitwig/sdl/main-native.cpp`

```cpp
#include "../core/sdl/SdlRunner.hpp"  // Réutilise SdlRunner de core
#include "app/AppLogic.hpp"
#include <oc/hal/midi/LibreMidiTransport.hpp>
#include <oc/hal/net/UdpTransport.hpp>

int main(int argc, char** argv) {
    SdlRunner runner;
    if (!runner.init(argc, argv)) return 1;

    // App avec MIDI + remote transport
    auto app = runner.appBuilder()
        .midi(std::make_unique<oc::hal::midi::LibreMidiTransport>(
            oc::hal::midi::LibreMidiConfig{.appName = "MIDI Studio Bitwig"}))
        .remote(std::make_unique<oc::hal::net::UdpTransport>(
            oc::hal::net::UdpConfig{.port = 9001}));

    // Contextes
    bitwig::app::registerContexts(app);
    app.begin();

    // Main loop
    while (runner.tick(app)) {}

    runner.shutdown();
    return 0;
}
```

### 4.2 Créer main-wasm.cpp pour plugin-bitwig

**Fichier à créer:** `plugin-bitwig/sdl/main-wasm.cpp`

```cpp
#include "../core/sdl/SdlRunner.hpp"
#include "app/AppLogic.hpp"
#include <oc/hal/midi/LibreMidiTransport.hpp>
#include <oc/hal/net/WebSocketTransport.hpp>
#include <emscripten.h>

static SdlRunner* g_runner = nullptr;
static oc::app::OpenControlApp* g_app = nullptr;

void mainLoop() {
    if (!g_runner->tick(*g_app)) {
        emscripten_cancel_main_loop();
    }
}

int main(int argc, char** argv) {
    static SdlRunner runner;
    g_runner = &runner;
    
    if (!runner.init(argc, argv)) return 1;

    static auto app = runner.appBuilder()
        .midi(std::make_unique<oc::hal::midi::LibreMidiTransport>())
        .remote(std::make_unique<oc::hal::net::WebSocketTransport>(
            oc::hal::net::WebSocketConfig{.url = "ws://localhost:9002"}));
    g_app = &app;

    bitwig::app::registerContexts(app);
    app.begin();

    emscripten_set_main_loop(mainLoop, 0, 1);
    return 0;
}
```

### 4.3 CMakeLists.txt pour plugin-bitwig SDL

**Option A:** Réutiliser core/sdl/CMakeLists.txt avec variables

**Option B:** Créer plugin-bitwig/sdl/CMakeLists.txt qui inclut les sources communes

À définir selon préférence.

---

## Phase 5: Transport factory sans ifdef

### 5.1 Structure des fichiers

```
core/sdl/
  transport/
    TransportFactory.hpp      → Interface commune
    NativeTransport.cpp       → Implémente avec UdpTransport
    WasmTransport.cpp         → Implémente avec WebSocketTransport
```

### 5.2 Interface

**Fichier:** `core/sdl/transport/TransportFactory.hpp`

```cpp
#pragma once
#include <memory>
#include <oc/hal/IMessageTransport.hpp>

namespace transport {

/// Crée le transport approprié pour la plateforme
/// Native: UdpTransport sur port 9001
/// WASM: WebSocketTransport vers ws://localhost:9002
std::unique_ptr<oc::hal::IMessageTransport> createRemoteTransport();

} // namespace transport
```

### 5.3 Sélection CMake

```cmake
if(EMSCRIPTEN)
    set(TRANSPORT_SRC transport/WasmTransport.cpp)
else()
    set(TRANSPORT_SRC transport/NativeTransport.cpp)
endif()
```

---

## Phase 6: WebSocket dans oc-bridge

### 6.1 Ajouter dépendance

**Fichier:** `oc-bridge/Cargo.toml`

```toml
[dependencies]
tokio-tungstenite = "0.21"
```

### 6.2 Configuration

**Fichier:** `oc-bridge/config/default.toml`

```toml
[bridge]
websocket_port = 9002  # 0 = disabled
```

### 6.3 Implémentation

- Listener WebSocket sur port configurable
- Route les messages WebSocket ↔ UDP (même format que Serial)
- Gère multiples connexions simultanées

---

## Ordre d'exécution

```
Phase 1 ✅ → Phase 2 → Phase 3 → Phase 4 → Test Native → Phase 5 → Phase 6 → Test WASM
```

| Phase | Effort estimé | Dépendances |
|-------|---------------|-------------|
| 1 ✅  | 30min         | - |
| 2     | 30min         | - |
| 3     | 1-2h          | Phase 2 |
| 4     | 1h            | Phase 3 |
| 5     | 30min         | Phase 4 |
| 6     | 3-4h          | Phase 5 (pour WASM) |

---

## Questions ouvertes

1. **CMakeLists plugin-bitwig:** Créer un nouveau fichier ou paramétrer celui de core?

2. **Chemin d'include SdlRunner:** plugin-bitwig référence `../core/sdl/SdlRunner.hpp` - OK ou créer un include path?

3. **State pour BitwigContext:** Pas de state externe nécessaire (BitwigState est interne). Confirmé?

4. **Config ports:** Hardcoder 9001/9002 ou configurable via args/env?
