# Phase 2 : RtMidiTransport - Plan d'Implémentation

## Objectif

Implémenter le support MIDI desktop via libremidi pour permettre la communication MIDI entre l'application desktop et des logiciels comme Bitwig via loopMIDI.

---

## Contexte Technique

### Bibliothèque choisie : libremidi v5.4.1

| Critère | Valeur |
|---------|--------|
| C++ minimum | C++20 |
| MIDI 2 | ✅ Supporté |
| Hotplug | ✅ Natif |
| Ports | Handles stables (pas d'index) |
| Header-only | ✅ Option disponible |

### Contraintes Windows

- Pas de ports MIDI virtuels natifs sur Windows
- Solution : loopMIDI (outil tiers) crée des ports virtuels
- L'app se connecte à loopMIDI, Bitwig aussi → communication établie

### Compatibilité C++17/C++20

```
Projet :
├── open-control/          → C++17 (code partagé)
├── hal-teensy/            → C++17 (ARM GCC)
├── hal-desktop/           → C++20 (libremidi)
└── midi-studio/core/
    ├── src/               → C++17 (code métier)
    └── desktop/           → C++20 (build CMake séparé)
```

Le code partagé reste C++17. Seul le build desktop passe en C++20.
C++20 est rétrocompatible, donc aucun problème.

---

## Philosophie Logging

### Principe

Le logging est **automatiquement initialisé** dans le constructeur de chaque `AppBuilder` HAL :
- **Teensy** : `setOutput(serialOutput())` → Serial
- **Desktop** : `setOutput(consoleOutput())` → std::cout

Le consommateur n'a **plus besoin** d'appeler `initLogging()` manuellement.

### Conditionnement

Le logging est conditionné par la macro `OC_LOG` :
- Défini dans `platformio.ini` (Teensy) : `-D OC_LOG`
- Défini dans `CMakeLists.txt` (Desktop) : `-DOC_LOG=1`
- Si non défini : macros `OC_LOG_*` sont no-op (zero-cost)

### Découplage waitForSerial (Teensy uniquement)

`waitForSerial()` reste disponible séparément si le consommateur veut attendre
la connexion Serial avant les logs de boot :

```cpp
void setup() {
    oc::hal::teensy::waitForSerial();  // Optionnel, manuel
    
    app = oc::hal::teensy::AppBuilder()  // setOutput() fait ici automatiquement
        .midi()
        // ...
}
```

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                        midi-studio/core                              │
│  ┌──────────────────┐      ┌──────────────────────────────────────┐ │
│  │  main.cpp Teensy  │      │ desktop/main.cpp                     │ │
│  │  - waitForSerial  │      │ - RtMidiConfig                       │ │
│  │    (optionnel)    │      │ - AppBuilder (auto-logging)          │ │
│  │  - AppBuilder     │      │                                      │ │
│  │    (auto-logging) │      │                                      │ │
│  └────────┬─────────┘      └────────────────┬─────────────────────┘ │
│           │                                  │                       │
│           │      ┌───────────────────────────┘                       │
│           │      │     CMakeLists.txt: C++20, libremidi, OC_LOG=1   │
└───────────│──────│───────────────────────────────────────────────────┘
            │      │
            ▼      ▼
┌───────────────────────┐    ┌────────────────────────────────────────┐
│  open-control/        │    │  open-control/hal-desktop              │
│  hal-teensy           │    │  ┌──────────────────────────────────┐  │
│  ┌─────────────────┐  │    │  │ src/oc/hal/desktop/              │  │
│  │ AppBuilder.hpp  │  │    │  │  ├── DesktopOutput.hpp           │  │
│  │ + setOutput()   │  │    │  │  ├── RtMidiTransport.hpp/.cpp    │  │
│  │   dans ctor     │  │    │  │  └── AppBuilder.hpp              │  │
│  └─────────────────┘  │    │  │      + setOutput() dans ctor     │  │
└───────────────────────┘    │  └──────────────────────────────────┘  │
            │                └────────────────────────────────────────┘
            │                                  │
            └──────────────┬───────────────────┘
                           ▼
┌─────────────────────────────────────────────────────────────────────┐
│                      open-control/framework                          │
│  ├── src/oc/hal/IMidiTransport.hpp   (interface)                    │
│  └── src/oc/log/Log.hpp              (logging API)                  │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Commits Planifiés

### Commit 1 : Logging auto dans AppBuilder Teensy

**Scope** : `hal-teensy`

**Fichier à modifier** : `src/oc/hal/teensy/AppBuilder.hpp`

**Changements** :

Dans le constructeur `AppBuilder()`, ajouter l'initialisation du logging :

```cpp
AppBuilder() {
    // Configure logging output (sans wait - découplé)
    oc::log::setOutput(serialOutput());
    
    // Register global time provider for oc::time::millis()
    oc::time::setProvider(defaultTimeProvider);
    // Configure app-level time provider
    builder_.timeProvider(defaultTimeProvider);
}
```

**Message** : `hal-teensy: auto-init logging in AppBuilder constructor`

---

### Commit 2 : Logging Desktop + intégration AppBuilder

**Scope** : `hal-desktop`

**Fichier à créer** : `src/oc/hal/desktop/DesktopOutput.hpp`

```cpp
#pragma once

/**
 * @file DesktopOutput.hpp
 * @brief Desktop-specific log output using std::cout
 */

#include <iostream>
#include <iomanip>
#include <chrono>
#include <oc/log/Log.hpp>

namespace oc::hal::desktop {

namespace {
    inline auto& getStartTime() {
        static auto start = std::chrono::steady_clock::now();
        return start;
    }
}

/**
 * @brief Get the console-based log output for Desktop
 */
inline const oc::log::Output& consoleOutput() {
    static const oc::log::Output output = {
        [](char c) { std::cout << c; },
        [](const char* str) { std::cout << str; },
        [](int32_t value) { std::cout << value; },
        [](uint32_t value) { std::cout << value; },
        [](float value) { std::cout << std::fixed << std::setprecision(4) << value; },
        [](bool value) { std::cout << (value ? "true" : "false"); },
        []() -> uint32_t {
            auto now = std::chrono::steady_clock::now();
            return static_cast<uint32_t>(
                std::chrono::duration_cast<std::chrono::milliseconds>(
                    now - getStartTime()
                ).count()
            );
        }
    };
    return output;
}

}  // namespace oc::hal::desktop
```

**Fichier à modifier** : `src/oc/hal/desktop/AppBuilder.hpp`

Dans le constructeur, ajouter l'initialisation du logging :

```cpp
#include <oc/hal/desktop/DesktopOutput.hpp>

// Dans le constructeur AppBuilder(InputMapper& input)
explicit AppBuilder(InputMapper& input) : input_(input) {
    // Configure logging output
    oc::log::setOutput(consoleOutput());
    
    initTime();
    builder_.timeProvider(defaultTimeProvider);

    buttonController_ = std::make_unique<SdlButtonController>();
    encoderController_ = std::make_unique<SdlEncoderController>();
}
```

**Message** : `hal-desktop: add DesktopOutput and auto-init logging in AppBuilder`

---

### Commit 3 : CMake C++20 + libremidi

**Scope** : `midi-studio/core`

**Fichier à modifier** : `desktop/CMakeLists.txt`

**Changements** :

1. Ligne 8 - Passer à C++20 :
```cmake
set(CMAKE_CXX_STANDARD 20)
```

2. Après SDL2 FetchContent (~ligne 114) - Ajouter libremidi :
```cmake
# ==============================================================================
# libremidi (FetchContent)
# ==============================================================================
message(STATUS "Fetching libremidi...")
FetchContent_Declare(
    libremidi
    GIT_REPOSITORY https://github.com/celtera/libremidi.git
    GIT_TAG        v5.4.1
    GIT_SHALLOW    TRUE
    GIT_PROGRESS   TRUE
)
set(LIBREMIDI_HEADER_ONLY ON CACHE BOOL "" FORCE)
set(LIBREMIDI_EXAMPLES OFF CACHE BOOL "" FORCE)
set(LIBREMIDI_TESTS OFF CACHE BOOL "" FORCE)
FetchContent_MakeAvailable(libremidi)
```

3. Ligne ~190 - Ajouter au link :
```cmake
target_link_libraries(midi_studio_desktop PRIVATE
    lvgl
    SDL2::SDL2-static
    libremidi
)
```

4. Ligne ~196 - Ajouter OC_LOG :
```cmake
target_compile_definitions(midi_studio_desktop PRIVATE 
    OC_DESKTOP=1
    OC_LOG=1
)
```

**Message** : `core/desktop: upgrade to C++20, add libremidi dependency`

---

### Commit 4 : RtMidiTransport

**Scope** : `hal-desktop`

**Fichiers à créer** :

#### 4.1 `src/oc/hal/desktop/RtMidiTransport.hpp`

```cpp
#pragma once

#include <cstddef>
#include <cstdint>
#include <memory>
#include <string>
#include <vector>

#include <oc/core/Result.hpp>
#include <oc/hal/IMidiTransport.hpp>

namespace libremidi {
class midi_in;
class midi_out;
class observer;
struct input_port;
struct output_port;
struct message;
}

namespace oc::hal::desktop {

/**
 * @brief Configuration for RtMidiTransport
 */
struct RtMidiConfig {
    /// Application name for port search and virtual port creation
    /// Default: "OpenControl" (framework name)
    /// Consumer should override: e.g., "MIDI Studio"
    std::string appName = "OpenControl";
    
    /// Input port name override ("" = auto-detect using appName, then first port)
    std::string inputPortName = "";
    
    /// Output port name override ("" = auto-detect using appName, then first port)
    std::string outputPortName = "";
    
    /// Create virtual ports if no matching port found (Linux/macOS only)
    bool createVirtualPorts = false;
    
    /// Maximum tracked active notes for allNotesOff()
    size_t maxActiveNotes = 32;
};

class RtMidiTransport : public hal::IMidiTransport {
public:
    RtMidiTransport() = default;
    explicit RtMidiTransport(const RtMidiConfig& config);
    ~RtMidiTransport() override;

    RtMidiTransport(const RtMidiTransport&) = delete;
    RtMidiTransport& operator=(const RtMidiTransport&) = delete;
    RtMidiTransport(RtMidiTransport&&) noexcept;
    RtMidiTransport& operator=(RtMidiTransport&&) noexcept;

    // Static helpers
    static std::vector<std::string> listInputPorts();
    static std::vector<std::string> listOutputPorts();

    // IMidiTransport
    core::Result<void> init() override;
    void update() override;

    void sendCC(uint8_t channel, uint8_t cc, uint8_t value) override;
    void sendNoteOn(uint8_t channel, uint8_t note, uint8_t velocity) override;
    void sendNoteOff(uint8_t channel, uint8_t note, uint8_t velocity) override;
    void sendSysEx(const uint8_t* data, size_t length) override;
    void sendProgramChange(uint8_t channel, uint8_t program) override;
    void sendPitchBend(uint8_t channel, int16_t value) override;
    void sendChannelPressure(uint8_t channel, uint8_t pressure) override;
    void allNotesOff() override;

    void setOnCC(CCCallback cb) override;
    void setOnNoteOn(NoteCallback cb) override;
    void setOnNoteOff(NoteCallback cb) override;
    void setOnSysEx(SysExCallback cb) override;

    // Status
    bool isInputOpen() const;
    bool isOutputOpen() const;
    std::string getInputPortName() const;
    std::string getOutputPortName() const;

private:
    struct ActiveNote {
        uint8_t channel;
        uint8_t note;
        bool active;
    };

    void handleIncomingMessage(const libremidi::message& msg);
    void markNoteActive(uint8_t channel, uint8_t note);
    void markNoteInactive(uint8_t channel, uint8_t note);

    RtMidiConfig config_;
    std::unique_ptr<libremidi::midi_in> midiIn_;
    std::unique_ptr<libremidi::midi_out> midiOut_;
    
    CCCallback onCC_;
    NoteCallback onNoteOn_;
    NoteCallback onNoteOff_;
    SysExCallback onSysEx_;

    std::vector<ActiveNote> activeNotes_;
    bool initialized_ = false;
    
    std::string currentInputPort_;
    std::string currentOutputPort_;
};

}  // namespace oc::hal::desktop
```

#### 4.2 `src/oc/hal/desktop/RtMidiTransport.cpp`

Implémentation complète (~280 lignes) :
- `init()` : Observer pour lister ports, ouvrir input/output
- `update()` : No-op (libremidi utilise callbacks async)
- `send*()` : Envoi via `midiOut_->send_message()`
- `handleIncomingMessage()` : Parse status byte, dispatch aux callbacks
- `allNotesOff()` : Envoie NoteOff pour toutes les notes trackées
- Logging via `OC_LOG_INFO`, `OC_LOG_DEBUG`, `OC_LOG_WARN`

Auto-detect (ordre de priorité) :
```cpp
// 1. Si inputPortName/outputPortName spécifié → utiliser directement
// 2. Sinon chercher un port contenant appName (ex: "MIDI Studio")
// 3. Sinon chercher ports connus : "loopMIDI", "IAC Driver"
// 4. Sinon premier port disponible
// 5. Sur Linux/macOS avec createVirtualPorts=true : créer port virtuel
```

#### 4.3 Modifier `src/oc/hal/desktop/AppBuilder.hpp`

Ajouter après la méthode `midi()` existante :

```cpp
#include <oc/hal/desktop/RtMidiTransport.hpp>

// ... dans la classe AppBuilder ...

/**
 * @brief Add real MIDI transport with configuration
 * 
 * @param config MIDI configuration (appName, ports, etc.)
 */
AppBuilder& midi(const RtMidiConfig& config) {
    builder_.midi(std::make_unique<RtMidiTransport>(config));
    return *this;
}

/**
 * @brief Add real MIDI transport with auto-detect (default appName: "OpenControl")
 */
AppBuilder& midiAuto() {
    builder_.midi(std::make_unique<RtMidiTransport>());
    return *this;
}
```

**Message** : `hal-desktop: add RtMidiTransport with libremidi`

---

### Commit 5 : Intégration consommateur

**Scope** : `midi-studio/core`

#### 5.1 Modifier `main.cpp` (Teensy)

Retirer l'appel manuel à `initLogging()` (maintenant fait dans AppBuilder) :

```cpp
void setup() {
    // OPTIONNEL : attendre Serial pour voir les logs de boot
    oc::hal::teensy::waitForSerial();
    
    // Plus besoin de : oc::hal::teensy::initLogging();
    // Le logging est initialisé automatiquement dans AppBuilder()
    
    OC_LOG_INFO("=== MIDI Studio Core Boot ===");
    // ... reste du code
}
```

#### 5.2 Modifier `desktop/main.cpp`

Plus besoin d'appeler `initLogging()` (fait dans AppBuilder).
Configurer le MIDI avec le nom de l'app :

```cpp
int main(int argc, char* argv[]) {
    (void)argc; (void)argv;
    using namespace Config;
    
    // Plus besoin de : oc::hal::desktop::initLogging();
    // Le logging est initialisé automatiquement dans AppBuilder()
    
    // ... code existant SDL, layout, etc ...
    
    // Build the app avec MIDI configuré
    oc::app::OpenControlApp app = oc::hal::desktop::AppBuilder(input)
        .controllers()
        .midi(oc::hal::desktop::RtMidiConfig{
            .appName = "MIDI Studio",     // Nom pour recherche/création port
            .inputPortName = "",          // Auto-detect
            .outputPortName = ""          // Auto-detect
        })
        .inputConfig(Config::Input::CONFIG);
    
    OC_LOG_INFO("MIDI Studio Desktop started");
    // ... reste du code
}
```

**Message** : `core: integrate auto-logging and configure MIDI for desktop`

---

### Commit 6 : Tests unitaires RtMidiTransport

**Scope** : `hal-desktop`

**Fichier à créer** : `test/test_rtmiditransport/test_rtmiditransport.cpp`

```cpp
#include <unity.h>
#include <oc/hal/desktop/RtMidiTransport.hpp>

using namespace oc::hal::desktop;

void test_config_defaults() {
    RtMidiConfig config;
    TEST_ASSERT_EQUAL_STRING("OpenControl", config.appName.c_str());
    TEST_ASSERT_TRUE(config.inputPortName.empty());
    TEST_ASSERT_TRUE(config.outputPortName.empty());
    TEST_ASSERT_FALSE(config.createVirtualPorts);
    TEST_ASSERT_EQUAL(32, config.maxActiveNotes);
}

void test_list_ports_returns_vector() {
    auto inputs = RtMidiTransport::listInputPorts();
    auto outputs = RtMidiTransport::listOutputPorts();
    // Just check it doesn't crash - ports may or may not exist
    TEST_ASSERT_TRUE(true);
}

void test_transport_init_without_ports() {
    RtMidiTransport transport;
    auto result = transport.init();
    // Should succeed even without ports (graceful degradation)
    TEST_ASSERT_TRUE(result.isOk());
    TEST_ASSERT_FALSE(transport.isInputOpen());
    TEST_ASSERT_FALSE(transport.isOutputOpen());
}

void test_transport_callbacks_not_crash() {
    RtMidiTransport transport;
    transport.setOnCC([](uint8_t, uint8_t, uint8_t) {});
    transport.setOnNoteOn([](uint8_t, uint8_t, uint8_t) {});
    transport.setOnNoteOff([](uint8_t, uint8_t, uint8_t) {});
    transport.setOnSysEx([](const uint8_t*, size_t) {});
    TEST_ASSERT_TRUE(true);
}

void test_send_methods_no_crash_when_not_connected() {
    RtMidiTransport transport;
    transport.init();
    // These should not crash even without connection
    transport.sendCC(0, 1, 127);
    transport.sendNoteOn(0, 60, 100);
    transport.sendNoteOff(0, 60, 0);
    transport.sendProgramChange(0, 5);
    transport.sendPitchBend(0, 0);
    transport.sendChannelPressure(0, 64);
    transport.allNotesOff();
    TEST_ASSERT_TRUE(true);
}

void setUp() {}
void tearDown() {}

int main() {
    UNITY_BEGIN();
    RUN_TEST(test_config_defaults);
    RUN_TEST(test_list_ports_returns_vector);
    RUN_TEST(test_transport_init_without_ports);
    RUN_TEST(test_transport_callbacks_not_crash);
    RUN_TEST(test_send_methods_no_crash_when_not_connected);
    return UNITY_END();
}
```

**Fichier à créer** : `test/test_rtmiditransport/platformio.ini` (ou intégrer dans le test existant)

**Message** : `hal-desktop: add RtMidiTransport unit tests`

---

## Validation

### Après chaque commit

```bash
# Build desktop
cd midi-studio/core/desktop
rm -rf build && mkdir build && cd build
cmake -G "MinGW Makefiles" -DCMAKE_BUILD_TYPE=Debug ..
cmake --build .
```

### Après Commit 1 (hal-teensy)

```bash
cd midi-studio/core
pio run -e dev
# Doit compiler sans erreur, logging auto dans AppBuilder
```

### Test final (après tous les commits)

1. Installer loopMIDI : https://www.tobias-erichsen.de/software/loopmidi.html
2. Créer un port virtuel nommé "MIDI Studio" (ou "loopMIDI")
3. Lancer l'app :
```bash
./bin/midi_studio_desktop
```
4. Vérifier dans la console :
   - `[XXms] INFO: MIDI Studio Desktop started`
   - `[XXms] INFO: MIDI Output opened: MIDI Studio`
   - `[XXms] INFO: MIDI Input opened: MIDI Studio`

5. Dans Bitwig :
   - Settings → Controllers
   - Ajouter contrôleur générique
   - Sélectionner "MIDI Studio" comme input/output
   - Envoyer un CC depuis l'app → voir dans Bitwig

### Tests unitaires

```bash
cd hal-desktop
pio test -e native
# Tous les tests doivent passer
```

---

## Résumé des fichiers

| Fichier | Action | Commit |
|---------|--------|--------|
| `hal-teensy/src/.../AppBuilder.hpp` | Modifier (+ setOutput) | 1 |
| `hal-desktop/src/.../DesktopOutput.hpp` | Créer | 2 |
| `hal-desktop/src/.../AppBuilder.hpp` | Modifier (+ setOutput) | 2 |
| `core/desktop/CMakeLists.txt` | Modifier (C++20 + libremidi) | 3 |
| `hal-desktop/src/.../RtMidiTransport.hpp` | Créer | 4 |
| `hal-desktop/src/.../RtMidiTransport.cpp` | Créer | 4 |
| `hal-desktop/src/.../AppBuilder.hpp` | Modifier (+ surcharges midi) | 4 |
| `core/main.cpp` | Modifier (- initLogging) | 5 |
| `core/desktop/main.cpp` | Modifier (MIDI config) | 5 |
| `hal-desktop/test/.../test_rtmiditransport.cpp` | Créer | 6 |

---

## Ordre des commits

| # | Repo | Message |
|---|------|---------|
| 1 | hal-teensy | `hal-teensy: auto-init logging in AppBuilder constructor` |
| 2 | hal-desktop | `hal-desktop: add DesktopOutput and auto-init logging in AppBuilder` |
| 3 | midi-studio/core | `core/desktop: upgrade to C++20, add libremidi dependency` |
| 4 | hal-desktop | `hal-desktop: add RtMidiTransport with libremidi` |
| 5 | midi-studio/core | `core: integrate auto-logging and configure MIDI for desktop` |
| 6 | hal-desktop | `hal-desktop: add RtMidiTransport unit tests` |

---

## Prochaines phases (référence)

- **Phase 3** : OC Bridge TCP sockets (Rust) - `open-control/bridge/`
- **Phase 4** : TcpSerialTransport dans hal-desktop

---

## Notes

- loopMIDI est requis sur Windows pour le développement
- Créer un port nommé "MIDI Studio" dans loopMIDI pour auto-detect
- Les logs sont colorés (ANSI) dans la console
- `OC_LOG=1` active le logging (défini par le consommateur)
- libremidi est téléchargé via FetchContent (pas de dépendance système)
- `appName` par défaut = "OpenControl" (framework), consommateur override avec son nom
- `waitForSerial()` sur Teensy reste manuel (optionnel, pour voir les logs de boot)
