# Plan de Migration : Refactoring Architecture open-control

**Version** : 2.0
**Date** : 2026-01-20
**Status** : Validé

---

## Table des matières

1. [Objectifs](#objectifs)
2. [Prérequis Git](#prérequis-git)
3. [Treeview Source (état actuel)](#treeview-source-état-actuel)
4. [Treeview Cible (état final)](#treeview-cible-état-final)
5. [Liste des changements](#liste-des-changements)
6. [Plan d'exécution par phases](#plan-dexécution-par-phases)
7. [Tracking](#tracking)

---

## Objectifs

1. **Séparer interfaces et implémentations** : `interface/` pour les contrats, `impl/` pour les implémentations universelles
2. **Clarifier les HALs** : hal-arduino (générique), hal-desktop (POSIX), hal-teensy (spécifique)
3. **Renommer hal-midi/hal-net** : Ce ne sont pas des HAL, ce sont des transports
4. **Réorganiser hal-teensy** : Sous-dossiers par domaine (storage/, io/, display/, hw/)
5. **Centraliser les interfaces** : Toutes les `I*.hpp` dans `framework/interface/`
6. **Pas de legacy** : Code clean uniquement, aucune rétrocompatibilité

---

## Prérequis Git

### Repos GitHub à RENOMMER

| Repo actuel | Nouveau nom | Action GitHub |
|-------------|-------------|---------------|
| `open-control/hal-embedded` | `open-control/hal-common` | Settings → Rename |
| `open-control/hal-midi` | `open-control/transport-midi` | Settings → Rename |
| `open-control/hal-net` | `open-control/transport-net` | Settings → Rename |

### Repos GitHub à CRÉER

| Nouveau repo | Description |
|--------------|-------------|
| `open-control/hal-arduino` | Generic Arduino HAL (GPIO, Time, Serial) |
| `open-control/hal-desktop` | Desktop HAL (POSIX filesystem) |

### Ordre des opérations Git

1. Faire les modifications locales (code)
2. Renommer les repos sur GitHub
3. Créer les nouveaux repos sur GitHub
4. Mettre à jour les remotes locaux
5. Push

---

## Treeview Source (état actuel)

```
open-control/
│
├── framework/                              [repo: open-control/framework]
│   ├── library.json
│   ├── platformio.ini
│   ├── README.md                           ← Contient anciens liens
│   └── src/oc/
│       ├── api/
│       │   ├── ButtonAPI.cpp
│       │   ├── ButtonAPI.hpp
│       │   ├── ButtonProxy.hpp
│       │   ├── EncoderAPI.cpp
│       │   ├── EncoderAPI.hpp
│       │   ├── EncoderProxy.hpp
│       │   ├── MidiAPI.cpp
│       │   └── MidiAPI.hpp
│       ├── app/
│       │   ├── AppBuilder.cpp
│       │   ├── AppBuilder.hpp
│       │   ├── OpenControlApp.cpp
│       │   └── OpenControlApp.hpp
│       ├── codec/
│       │   └── CobsCodec.hpp
│       ├── context/
│       │   ├── APIs.hpp
│       │   ├── ContextManager.cpp
│       │   ├── ContextManager.hpp
│       │   ├── IContext.hpp                ← Move to interface/
│       │   ├── IContextSwitcher.hpp        ← Move to interface/
│       │   └── Requirements.hpp
│       ├── core/
│       │   ├── Result.hpp
│       │   ├── Warning.hpp
│       │   ├── event/
│       │   │   ├── Event.hpp
│       │   │   ├── EventBus.cpp
│       │   │   ├── EventBus.hpp
│       │   │   ├── Events.hpp
│       │   │   ├── EventTypes.hpp
│       │   │   └── IEventBus.hpp           ← Move to interface/
│       │   ├── input/
│       │   │   ├── AuthorityResolver.hpp
│       │   │   ├── BindingHandle.cpp
│       │   │   ├── BindingHandle.hpp
│       │   │   ├── ButtonBuilder.cpp
│       │   │   ├── ButtonBuilder.hpp
│       │   │   ├── ComboBuilder.cpp
│       │   │   ├── ComboBuilder.hpp
│       │   │   ├── EncoderBuilder.cpp
│       │   │   ├── EncoderBuilder.hpp
│       │   │   ├── EncoderLogic.cpp
│       │   │   ├── EncoderLogic.hpp
│       │   │   ├── InputBinding.cpp
│       │   │   ├── InputBinding.hpp
│       │   │   └── InputConfig.hpp
│       │   └── struct/
│       │       └── Binding.hpp
│       ├── debug/
│       │   └── InvariantAssert.hpp
│       ├── hal/                            ← DELETE after moves
│       │   ├── FileStorageBackend.hpp      ← Move to hal-desktop/
│       │   ├── IButtonController.hpp       ← Move to interface/
│       │   ├── IDisplayDriver.hpp          ← Move to interface/
│       │   ├── IEncoderController.hpp      ← Move to interface/
│       │   ├── IEncoderHardware.hpp        ← Move to interface/
│       │   ├── IFrameTransport.hpp         ← Move to interface/
│       │   ├── IGpio.hpp                   ← Move to interface/
│       │   ├── IMidiTransport.hpp          ← Move to interface/
│       │   ├── IMultiplexer.hpp            ← Move to interface/
│       │   ├── IStorageBackend.hpp         ← Move to interface/
│       │   ├── NullMidiTransport.hpp       ← Move to impl/
│       │   └── Types.hpp                   ← Move to interface/
│       ├── log/
│       │   ├── Log.cpp
│       │   ├── Log.hpp
│       │   └── ProtocolOutput.hpp
│       ├── state/
│       │   ├── AutoPersist.hpp
│       │   ├── AutoPersistIncremental.hpp
│       │   ├── Bind.hpp
│       │   ├── DerivedSignal.hpp
│       │   ├── ExclusiveVisibilityStack.hpp
│       │   ├── NotificationQueue.cpp
│       │   ├── NotificationQueue.hpp
│       │   ├── Settings.hpp
│       │   ├── Signal.hpp
│       │   ├── SignalString.hpp
│       │   ├── SignalVector.hpp
│       │   └── SignalWatcher.hpp
│       ├── time/
│       │   ├── Time.cpp
│       │   └── Time.hpp
│       ├── util/
│       │   └── Index.hpp
│       └── Config.hpp
│
├── hal-embedded/                           [repo: open-control/hal-embedded] → RENAME
│   ├── library.json                        ← Update URL
│   ├── platformio.ini                      ← Update deps
│   ├── src/
│   │   ├── main.cpp                        ← DELETE
│   │   └── oc/hal/embedded/
│   │       ├── ButtonDef.hpp
│       │   ├── EncoderDef.hpp
│       │   ├── GpioPin.hpp
│       │   └── Types.hpp
│
├── hal-midi/                               [repo: open-control/hal-midi] → RENAME
│   ├── library.json                        ← Update URL
│   └── src/oc/hal/midi/
│       ├── LibreMidiTransport.cpp
│       └── LibreMidiTransport.hpp
│
├── hal-net/                                [repo: open-control/hal-net] → RENAME
│   ├── library.json                        ← Update URL
│   └── src/oc/hal/net/
│       ├── UdpTransport.cpp
│       ├── UdpTransport.hpp
│       ├── WebSocketTransport.cpp
│       └── WebSocketTransport.hpp
│
├── hal-sdl/                                [repo: open-control/hal-sdl]
│   ├── library.json
│   └── src/oc/hal/sdl/
│       ├── AppBuilder.hpp
│       ├── InputMapper.cpp
│       ├── InputMapper.hpp
│       ├── SdlButtonController.hpp
│       ├── SdlEncoderController.hpp
│       ├── Sdl.hpp
│       ├── SdlOutput.hpp
│       └── SdlTime.hpp
│
├── hal-teensy/                             [repo: open-control/hal-teensy]
│   ├── library.json                        ← Update deps
│   ├── platformio.ini                      ← Update deps
│   ├── README.md                           ← Update links
│   └── src/
│       ├── main.cpp                        ← Move to examples/
│       └── oc/hal/teensy/
│           ├── AppBuilder.hpp
│           ├── ButtonController.hpp
│           ├── EEPROMBackend.hpp
│           ├── EncoderController.hpp
│           ├── EncoderToolHardware.hpp
│           ├── flash/                      ← DELETE (empty)
│           ├── GenericMux.hpp
│           ├── Ili9341.cpp
│           ├── Ili9341.hpp
│           ├── LittleFSBackend.hpp
│           ├── SDCardBackend.hpp
│           ├── TeensyGpio.hpp              ← DELETE (→ hal-arduino)
│           ├── Teensy.hpp
│           ├── TeensyOutput.hpp
│           ├── UsbMidi.cpp
│           ├── UsbMidi.hpp
│           └── UsbSerial.hpp
│
├── ui-lvgl/                                [repo: open-control/ui-lvgl]
│   ├── library.json
│   ├── platformio.ini
│   ├── README.md
│   └── src/
│       ├── main.cpp                        ← Move to examples/
│       └── oc/ui/lvgl/
│           ├── Bridge.cpp
│           ├── Bridge.hpp
│           ├── FontLoader.cpp
│           ├── FontLoader.hpp
│           ├── FontUtils.cpp
│           ├── FontUtils.hpp
│           ├── IComponent.hpp
│           ├── IElement.hpp
│           ├── IListItem.hpp
│           ├── IView.hpp
│           ├── IWidget.hpp
│           ├── Scope.hpp
│           ├── Screen.cpp
│           ├── Screen.hpp
│           ├── SdlBridge.cpp
│           └── SdlBridge.hpp
│
├── ui-lvgl-components/                     [repo: open-control/ui-lvgl-components]
│   ├── README.md                           ← Update links
│   └── ...
│
├── example-teensy41-minimal/               [repo: open-control/example-teensy41-minimal]
│   ├── README.md                           ← Update links
│   ├── platformio.ini                      ← Update deps
│   └── include/Config.hpp                  ← BROKEN: uses oc/hal/common/
│
├── example-teensy41-lvgl/                  [repo: open-control/example-teensy41-lvgl]
│   ├── README.md                           ← Update links
│   ├── platformio.ini                      ← Update deps
│   └── include/Config.hpp                  ← BROKEN: uses oc/hal/common/
│
├── example-teensy41-01-midi-output/
│   └── platformio.ini                      ← Update deps
│
├── example-teensy41-02-encoders/
│   ├── platformio.ini                      ← Update deps
│   └── src/main.cpp                        ← BROKEN: uses oc/hal/common/
│
├── example-teensy41-03-buttons/
│   └── platformio.ini                      ← Update deps
│
├── protocol-codegen/                       [repo: open-control/protocol-codegen]
│   ├── README.md                           ← Update links
│   └── src/protocol_codegen/generators/
│       ├── protocols/binary/framing.py     ← Update templates
│       └── binary/cpp/protocol_generator.py ← Update templates
│
├── bridge/                                 [repo: open-control/bridge]
│   └── README.md                           ← Update links
│
├── .github/profile/README.md               ← Update links (already mentions hal-common)
│
└── example-00-architecture/
    └── CHEATSHEET.md                       ← Update examples
```

---

## Treeview Cible (état final)

```
open-control/
│
├── framework/                              [repo: open-control/framework]
│   ├── library.json
│   ├── platformio.ini
│   ├── README.md
│   └── src/oc/
│       │
│       ├── interface/                      ── ALL INTERFACES ──
│       │   ├── IButton.hpp                 ← from hal/IButtonController.hpp
│       │   ├── IContext.hpp                ← from context/IContext.hpp
│       │   ├── IContextSwitcher.hpp        ← from context/IContextSwitcher.hpp
│       │   ├── IDisplay.hpp                ← from hal/IDisplayDriver.hpp
│       │   ├── IEncoder.hpp                ← from hal/IEncoderController.hpp
│       │   ├── IEncoderHardware.hpp        ← from hal/IEncoderHardware.hpp
│       │   ├── IEventBus.hpp               ← from core/event/IEventBus.hpp
│       │   ├── IGpio.hpp                   ← from hal/IGpio.hpp
│       │   ├── IMidi.hpp                   ← from hal/IMidiTransport.hpp
│       │   ├── IMultiplexer.hpp            ← from hal/IMultiplexer.hpp
│       │   ├── IStorage.hpp                ← from hal/IStorageBackend.hpp
│       │   ├── ITransport.hpp              ← from hal/IFrameTransport.hpp
│       │   └── Types.hpp                   ← from hal/Types.hpp
│       │
│       ├── impl/                           ── UNIVERSAL IMPLEMENTATIONS ──
│       │   ├── MemoryStorage.hpp           ← NEW (based on midi-studio)
│       │   ├── NullMidi.hpp                ← from hal/NullMidiTransport.hpp
│       │   └── NullStorage.hpp             ← NEW
│       │
│       ├── api/                            (unchanged)
│       ├── app/                            (unchanged)
│       ├── codec/                          (unchanged)
│       ├── context/                        (I*.hpp removed)
│       │   ├── APIs.hpp
│       │   ├── ContextManager.cpp
│       │   ├── ContextManager.hpp
│       │   └── Requirements.hpp
│       ├── core/                           (IEventBus.hpp removed)
│       ├── debug/                          (unchanged)
│       ├── log/                            (unchanged)
│       ├── state/                          (unchanged)
│       ├── time/                           (unchanged)
│       ├── util/                           (unchanged)
│       └── Config.hpp
│
├── hal-arduino/                            ── NEW REPO ──
│   ├── library.json
│   └── src/oc/hal/arduino/
│       ├── ArduinoGpio.hpp
│       ├── ArduinoTime.hpp
│       └── ArduinoSerial.hpp
│
├── hal-common/                             ── RENAMED from hal-embedded ──
│   ├── library.json
│   ├── platformio.ini
│   └── src/oc/hal/common/
│       └── embedded/
│           ├── ButtonDef.hpp
│           ├── EncoderDef.hpp
│           ├── GpioPin.hpp
│           └── Types.hpp
│
├── hal-desktop/                            ── NEW REPO ──
│   ├── library.json
│   └── src/oc/hal/desktop/
│       └── FileStorage.hpp
│
├── hal-sdl/                                (includes updated)
│   ├── library.json
│   └── src/oc/hal/sdl/
│       └── ... (same files)
│
├── hal-teensy/                             (reorganized)
│   ├── library.json
│   ├── platformio.ini
│   ├── examples/test/main.cpp
│   └── src/oc/hal/teensy/
│       ├── storage/
│       │   ├── EEPROMBackend.hpp
│       │   ├── LittleFSBackend.hpp
│       │   └── SDCardBackend.hpp
│       ├── io/
│       │   ├── UsbMidi.cpp
│       │   ├── UsbMidi.hpp
│       │   └── UsbSerial.hpp
│       ├── display/
│       │   ├── Ili9341.cpp
│       │   └── Ili9341.hpp
│       ├── hw/
│       │   ├── ButtonController.hpp
│       │   ├── EncoderController.hpp
│       │   ├── EncoderToolHardware.hpp
│       │   └── GenericMux.hpp
│       ├── AppBuilder.hpp
│       ├── Teensy.hpp
│       └── TeensyOutput.hpp
│
├── transport-midi/                         ── RENAMED from hal-midi ──
│   ├── library.json
│   └── src/oc/transport/midi/
│       ├── LibreMidiTransport.cpp
│       └── LibreMidiTransport.hpp
│
├── transport-net/                          ── RENAMED from hal-net ──
│   ├── library.json
│   └── src/oc/transport/net/
│       ├── UdpTransport.cpp
│       ├── UdpTransport.hpp
│       ├── WebSocketTransport.cpp
│       └── WebSocketTransport.hpp
│
├── ui-lvgl/                                (reorganized)
│   ├── library.json
│   ├── platformio.ini
│   ├── examples/demo/main.cpp
│   └── src/oc/ui/lvgl/
│       ├── interface/
│       │   ├── IComponent.hpp
│       │   ├── IElement.hpp
│       │   ├── IListItem.hpp
│       │   ├── IView.hpp
│       │   └── IWidget.hpp
│       ├── bridge/
│       │   ├── Bridge.cpp
│       │   ├── Bridge.hpp
│       │   ├── SdlBridge.cpp
│       │   └── SdlBridge.hpp
│       ├── font/
│       │   ├── FontLoader.cpp
│       │   ├── FontLoader.hpp
│       │   ├── FontUtils.cpp
│       │   └── FontUtils.hpp
│       ├── Screen.cpp
│       ├── Screen.hpp
│       └── Scope.hpp
│
├── ui-lvgl-components/                     (unchanged, links updated)
├── example-teensy41-*/                     (includes updated)
├── protocol-codegen/                       (templates updated)
├── bridge/                                 (unchanged, links updated)
└── .github/profile/README.md               (already correct)
```

---

## Liste des changements

### A. Classes à RENOMMER

| Ancien nom | Nouveau nom | Fichier |
|------------|-------------|---------|
| `IButtonController` | `IButton` | interface/IButton.hpp |
| `IDisplayDriver` | `IDisplay` | interface/IDisplay.hpp |
| `IEncoderController` | `IEncoder` | interface/IEncoder.hpp |
| `IFrameTransport` | `ITransport` | interface/ITransport.hpp |
| `IMidiTransport` | `IMidi` | interface/IMidi.hpp |
| `IStorageBackend` | `IStorage` | interface/IStorage.hpp |
| `NullMidiTransport` | `NullMidi` | impl/NullMidi.hpp |
| `FileStorageBackend` | `FileStorage` | hal-desktop/.../FileStorage.hpp |

### B. Namespaces à MODIFIER

| Ancien namespace | Nouveau namespace |
|------------------|-------------------|
| `oc::hal` (pour interfaces) | `oc` |
| `oc::hal::embedded` | `oc::hal::common::embedded` |
| `oc::hal::midi` | `oc::transport::midi` |
| `oc::hal::net` | `oc::transport::net` |
| `oc::hal` (NullMidiTransport) | `oc::impl` |
| `oc::hal` (FileStorageBackend) | `oc::hal::desktop` |

### C. Mapping des includes

| Ancien include | Nouveau include |
|----------------|-----------------|
| `oc/hal/IButtonController.hpp` | `oc/interface/IButton.hpp` |
| `oc/hal/IDisplayDriver.hpp` | `oc/interface/IDisplay.hpp` |
| `oc/hal/IEncoderController.hpp` | `oc/interface/IEncoder.hpp` |
| `oc/hal/IEncoderHardware.hpp` | `oc/interface/IEncoderHardware.hpp` |
| `oc/hal/IFrameTransport.hpp` | `oc/interface/ITransport.hpp` |
| `oc/hal/IGpio.hpp` | `oc/interface/IGpio.hpp` |
| `oc/hal/IMidiTransport.hpp` | `oc/interface/IMidi.hpp` |
| `oc/hal/IMultiplexer.hpp` | `oc/interface/IMultiplexer.hpp` |
| `oc/hal/IStorageBackend.hpp` | `oc/interface/IStorage.hpp` |
| `oc/hal/Types.hpp` | `oc/interface/Types.hpp` |
| `oc/hal/NullMidiTransport.hpp` | `oc/impl/NullMidi.hpp` |
| `oc/hal/FileStorageBackend.hpp` | `oc/hal/desktop/FileStorage.hpp` |
| `oc/context/IContext.hpp` | `oc/interface/IContext.hpp` |
| `oc/context/IContextSwitcher.hpp` | `oc/interface/IContextSwitcher.hpp` |
| `oc/core/event/IEventBus.hpp` | `oc/interface/IEventBus.hpp` |
| `oc/hal/embedded/*` | `oc/hal/common/embedded/*` |
| `oc/hal/common/ButtonDef.hpp` | `oc/hal/common/embedded/ButtonDef.hpp` | ⚠️ FIX examples cassés |
| `oc/hal/common/EncoderDef.hpp` | `oc/hal/common/embedded/EncoderDef.hpp` | ⚠️ FIX examples cassés |
| `oc/hal/common/GpioPin.hpp` | `oc/hal/common/embedded/GpioPin.hpp` | ⚠️ FIX examples cassés |
| `oc/hal/common/Types.hpp` | `oc/hal/common/embedded/Types.hpp` | ⚠️ FIX examples cassés |
| `oc/hal/midi/*` | `oc/transport/midi/*` |
| `oc/hal/net/*` | `oc/transport/net/*` |
| `oc/hal/teensy/TeensyGpio.hpp` | `oc/hal/arduino/ArduinoGpio.hpp` |
| `oc/hal/teensy/GenericMux.hpp` | `oc/hal/teensy/hw/GenericMux.hpp` |
| `oc/hal/teensy/Ili9341.hpp` | `oc/hal/teensy/display/Ili9341.hpp` |
| `oc/hal/teensy/UsbMidi.hpp` | `oc/hal/teensy/io/UsbMidi.hpp` |
| `oc/hal/teensy/UsbSerial.hpp` | `oc/hal/teensy/io/UsbSerial.hpp` |
| `oc/hal/teensy/SDCardBackend.hpp` | `oc/hal/teensy/storage/SDCardBackend.hpp` |
| `oc/hal/teensy/EEPROMBackend.hpp` | `oc/hal/teensy/storage/EEPROMBackend.hpp` |
| `oc/hal/teensy/LittleFSBackend.hpp` | `oc/hal/teensy/storage/LittleFSBackend.hpp` |
| `oc/hal/teensy/ButtonController.hpp` | `oc/hal/teensy/hw/ButtonController.hpp` |
| `oc/hal/teensy/EncoderController.hpp` | `oc/hal/teensy/hw/EncoderController.hpp` |
| `oc/hal/teensy/EncoderToolHardware.hpp` | `oc/hal/teensy/hw/EncoderToolHardware.hpp` |

### D. URLs GitHub à mettre à jour

| Fichier | Ancien pattern | Nouveau pattern |
|---------|----------------|-----------------|
| `hal-embedded/library.json` | `hal-embedded.git` | `hal-common.git` |
| `hal-midi/library.json` | `hal-midi.git` | `transport-midi.git` |
| `hal-net/library.json` | `hal-net.git` | `transport-net.git` |
| `hal-teensy/platformio.ini` | `hal-embedded` | `hal-common` |
| `example-*/platformio.ini` | `hal-teensy` | `hal-teensy` (unchanged) |
| `example-*/README.md` | `hal-common.git` | `hal-common.git` (already correct) |

### E. Fichiers à SUPPRIMER

| Fichier | Raison |
|---------|--------|
| `framework/src/oc/hal/` | Vide après déplacements |
| `hal-teensy/.../TeensyGpio.hpp` | Remplacé par hal-arduino |
| `hal-teensy/.../flash/` | Dossier vide |
| `hal-teensy/src/main.cpp` | Déplacé vers examples/ |
| `hal-common/src/main.cpp` | Inutile |
| `ui-lvgl/src/main.cpp` | Déplacé vers examples/ |

---

## Plan d'exécution par phases

### PHASE 1 : Framework (interface/ + impl/)

**Dépendances** : Aucune
**Validation** : `cd framework && pio run -e native`

#### 1.1 Créer les dossiers

```bash
cd /home/simon/petitechose-audio/workspace/open-control/framework/src/oc
mkdir -p interface impl
```

#### 1.2 Déplacer les interfaces depuis hal/

```bash
git mv hal/IButtonController.hpp interface/IButton.hpp
git mv hal/IDisplayDriver.hpp interface/IDisplay.hpp
git mv hal/IEncoderController.hpp interface/IEncoder.hpp
git mv hal/IEncoderHardware.hpp interface/IEncoderHardware.hpp
git mv hal/IFrameTransport.hpp interface/ITransport.hpp
git mv hal/IGpio.hpp interface/IGpio.hpp
git mv hal/IMidiTransport.hpp interface/IMidi.hpp
git mv hal/IMultiplexer.hpp interface/IMultiplexer.hpp
git mv hal/IStorageBackend.hpp interface/IStorage.hpp
git mv hal/Types.hpp interface/Types.hpp
```

#### 1.3 Déplacer les interfaces depuis context/ et core/

```bash
git mv context/IContext.hpp interface/IContext.hpp
git mv context/IContextSwitcher.hpp interface/IContextSwitcher.hpp
git mv core/event/IEventBus.hpp interface/IEventBus.hpp
```

#### 1.4 Déplacer NullMidiTransport vers impl/

```bash
git mv hal/NullMidiTransport.hpp impl/NullMidi.hpp
```

#### 1.5 Créer NullStorage.hpp

```cpp
// framework/src/oc/impl/NullStorage.hpp
#pragma once

#include <oc/interface/IStorage.hpp>
#include <cstring>

namespace oc::impl {

class NullStorage : public IStorage {
public:
    bool begin() override { return true; }
    bool available() const override { return true; }

    size_t read(uint32_t, uint8_t* buffer, size_t size) override {
        std::memset(buffer, 0xFF, size);
        return size;
    }

    size_t write(uint32_t, const uint8_t*, size_t size) override {
        return size;
    }

    bool commit() override { return true; }
    bool erase(uint32_t, size_t) override { return true; }
    size_t capacity() const override { return 64 * 1024; }
};

}  // namespace oc::impl
```

#### 1.6 Créer MemoryStorage.hpp

```cpp
// framework/src/oc/impl/MemoryStorage.hpp
#pragma once

#include <oc/interface/IStorage.hpp>
#include <vector>
#include <cstring>
#include <algorithm>

namespace oc::impl {

class MemoryStorage : public IStorage {
public:
    explicit MemoryStorage(size_t capacity = 4096) : data_(capacity, 0xFF) {}

    bool begin() override { return true; }
    bool available() const override { return true; }

    size_t read(uint32_t address, uint8_t* buffer, size_t size) override {
        if (address >= data_.size()) return 0;
        size_t toRead = std::min(size, data_.size() - address);
        std::memcpy(buffer, data_.data() + address, toRead);
        return toRead;
    }

    size_t write(uint32_t address, const uint8_t* buffer, size_t size) override {
        if (address >= data_.size()) return 0;
        size_t toWrite = std::min(size, data_.size() - address);
        std::memcpy(data_.data() + address, buffer, toWrite);
        return toWrite;
    }

    bool commit() override { return true; }

    bool erase(uint32_t address, size_t size) override {
        if (address >= data_.size()) return false;
        size_t toErase = std::min(size, data_.size() - address);
        std::memset(data_.data() + address, 0xFF, toErase);
        return true;
    }

    size_t capacity() const override { return data_.size(); }

private:
    std::vector<uint8_t> data_;
};

}  // namespace oc::impl
```

#### 1.7 Renommer les classes dans les fichiers interface/

Dans chaque fichier, renommer :
- `IButtonController` → `IButton`
- `IDisplayDriver` → `IDisplay`
- `IEncoderController` → `IEncoder`
- `IFrameTransport` → `ITransport`
- `IMidiTransport` → `IMidi`
- `IStorageBackend` → `IStorage`

Et changer le namespace `oc::hal` → `oc` pour les interfaces.

#### 1.8 Renommer la classe dans impl/NullMidi.hpp

- `NullMidiTransport` → `NullMidi`
- Namespace `oc::hal` → `oc::impl`
- Include `oc/hal/IMidiTransport.hpp` → `oc/interface/IMidi.hpp`

#### 1.9 Mettre à jour les includes dans framework/

```bash
cd /home/simon/petitechose-audio/workspace/open-control

find framework/src -type f \( -name "*.hpp" -o -name "*.cpp" \) -exec sed -i \
  -e 's|#include <oc/hal/IButtonController\.hpp>|#include <oc/interface/IButton.hpp>|g' \
  -e 's|#include <oc/hal/IDisplayDriver\.hpp>|#include <oc/interface/IDisplay.hpp>|g' \
  -e 's|#include <oc/hal/IEncoderController\.hpp>|#include <oc/interface/IEncoder.hpp>|g' \
  -e 's|#include <oc/hal/IEncoderHardware\.hpp>|#include <oc/interface/IEncoderHardware.hpp>|g' \
  -e 's|#include <oc/hal/IFrameTransport\.hpp>|#include <oc/interface/ITransport.hpp>|g' \
  -e 's|#include <oc/hal/IGpio\.hpp>|#include <oc/interface/IGpio.hpp>|g' \
  -e 's|#include <oc/hal/IMidiTransport\.hpp>|#include <oc/interface/IMidi.hpp>|g' \
  -e 's|#include <oc/hal/IMultiplexer\.hpp>|#include <oc/interface/IMultiplexer.hpp>|g' \
  -e 's|#include <oc/hal/IStorageBackend\.hpp>|#include <oc/interface/IStorage.hpp>|g' \
  -e 's|#include <oc/hal/Types\.hpp>|#include <oc/interface/Types.hpp>|g' \
  -e 's|#include <oc/hal/NullMidiTransport\.hpp>|#include <oc/impl/NullMidi.hpp>|g' \
  -e 's|#include <oc/context/IContext\.hpp>|#include <oc/interface/IContext.hpp>|g' \
  -e 's|#include <oc/context/IContextSwitcher\.hpp>|#include <oc/interface/IContextSwitcher.hpp>|g' \
  -e 's|#include <oc/core/event/IEventBus\.hpp>|#include <oc/interface/IEventBus.hpp>|g' \
  {} \;

# Renommer les classes
find framework/src -type f \( -name "*.hpp" -o -name "*.cpp" \) -exec sed -i \
  -e 's|\bIButtonController\b|IButton|g' \
  -e 's|\bIDisplayDriver\b|IDisplay|g' \
  -e 's|\bIEncoderController\b|IEncoder|g' \
  -e 's|\bIFrameTransport\b|ITransport|g' \
  -e 's|\bIMidiTransport\b|IMidi|g' \
  -e 's|\bIStorageBackend\b|IStorage|g' \
  -e 's|\bNullMidiTransport\b|NullMidi|g' \
  {} \;
```

#### 1.10 Supprimer framework/hal/

```bash
# Sauvegarder FileStorageBackend.hpp pour hal-desktop AVANT de supprimer
cp framework/src/oc/hal/FileStorageBackend.hpp /tmp/

rm -rf framework/src/oc/hal
```

---

### PHASE 2 : HALs (hal-common, transport-*, hal-arduino, hal-desktop, hal-sdl)

**Dépendances** : Phase 1 (framework)
**Validation** : `grep -r "oc::hal::" hal-common transport-midi transport-net` doit être vide

#### 2.1 hal-common (renommer hal-embedded) - EN PREMIER

```bash
cd /home/simon/petitechose-audio/workspace/open-control

# Renommer le dossier
git mv hal-embedded hal-common

# Créer la structure cible
mkdir -p hal-common/src/oc/hal/common

# Déplacer embedded/
git mv hal-common/src/oc/hal/embedded hal-common/src/oc/hal/common/embedded

# Supprimer main.cpp
rm hal-common/src/main.cpp

# Mettre à jour les namespaces
find hal-common -type f -name "*.hpp" -exec sed -i \
  's|namespace oc::hal::embedded|namespace oc::hal::common::embedded|g' {} \;

# Mettre à jour les includes internes
find hal-common -type f -name "*.hpp" -exec sed -i \
  -e 's|#include <oc/hal/embedded/|#include <oc/hal/common/embedded/|g' \
  -e 's|#include <oc/hal/Types\.hpp>|#include <oc/interface/Types.hpp>|g' \
  {} \;
```

Mettre à jour `hal-common/library.json` :
```json
{
  "name": "hal-common",
  "version": "0.2.0",
  "description": "Common embedded types for Open Control HAL",
  "repository": {
    "type": "git",
    "url": "https://github.com/open-control/hal-common.git"
  },
  "dependencies": {
    "framework": "https://github.com/open-control/framework.git"
  }
}
```

#### 2.2 transport-midi (renommer hal-midi)

```bash
git mv hal-midi transport-midi

mkdir -p transport-midi/src/oc/transport
git mv transport-midi/src/oc/hal/midi transport-midi/src/oc/transport/midi
rmdir transport-midi/src/oc/hal

find transport-midi -type f \( -name "*.hpp" -o -name "*.cpp" \) -exec sed -i \
  -e 's|namespace oc::hal::midi|namespace oc::transport::midi|g' \
  -e 's|oc::hal::midi|oc::transport::midi|g' \
  -e 's|#include <oc/hal/IMidiTransport\.hpp>|#include <oc/interface/IMidi.hpp>|g' \
  -e 's|\bIMidiTransport\b|IMidi|g' \
  {} \;
```

Mettre à jour `transport-midi/library.json` :
```json
{
  "name": "transport-midi",
  "version": "0.1.0",
  "description": "MIDI transport for Open Control (libremidi)",
  "repository": {
    "type": "git",
    "url": "https://github.com/open-control/transport-midi.git"
  },
  "dependencies": {
    "framework": "*"
  }
}
```

#### 2.3 transport-net (renommer hal-net)

```bash
git mv hal-net transport-net

mkdir -p transport-net/src/oc/transport
git mv transport-net/src/oc/hal/net transport-net/src/oc/transport/net
rmdir transport-net/src/oc/hal

find transport-net -type f \( -name "*.hpp" -o -name "*.cpp" \) -exec sed -i \
  -e 's|namespace oc::hal::net|namespace oc::transport::net|g' \
  -e 's|oc::hal::net|oc::transport::net|g' \
  -e 's|#include <oc/hal/IFrameTransport\.hpp>|#include <oc/interface/ITransport.hpp>|g' \
  -e 's|\bIFrameTransport\b|ITransport|g' \
  {} \;
```

Mettre à jour `transport-net/library.json` :
```json
{
  "name": "transport-net",
  "version": "0.1.0",
  "description": "Network transports for Open Control (UDP, WebSocket)",
  "repository": {
    "type": "git",
    "url": "https://github.com/open-control/transport-net.git"
  },
  "dependencies": {
    "framework": "*"
  }
}
```

#### 2.4 hal-arduino (nouveau)

```bash
mkdir -p hal-arduino/src/oc/hal/arduino
```

Créer `hal-arduino/src/oc/hal/arduino/ArduinoGpio.hpp` :
```cpp
#pragma once

#include <Arduino.h>
#include <oc/interface/IGpio.hpp>

namespace oc::hal::arduino {

class ArduinoGpio : public oc::IGpio {
public:
    void pinMode(uint8_t pin, oc::PinMode mode) override {
        switch (mode) {
            case oc::PinMode::PIN_INPUT: ::pinMode(pin, INPUT); break;
            case oc::PinMode::PIN_INPUT_PULLUP: ::pinMode(pin, INPUT_PULLUP); break;
            case oc::PinMode::PIN_OUTPUT: ::pinMode(pin, OUTPUT); break;
        }
    }

    void digitalWrite(uint8_t pin, bool high) override {
        ::digitalWrite(pin, high ? HIGH : LOW);
    }

    bool digitalRead(uint8_t pin) override {
        return ::digitalRead(pin) == HIGH;
    }

    uint16_t analogRead(uint8_t pin) override {
        return ::analogRead(pin);
    }
};

inline ArduinoGpio& gpio() {
    static ArduinoGpio instance;
    return instance;
}

}  // namespace oc::hal::arduino
```

Créer `hal-arduino/src/oc/hal/arduino/ArduinoTime.hpp` :
```cpp
#pragma once

#include <Arduino.h>

namespace oc::hal::arduino {

inline uint32_t millis() { return ::millis(); }
inline uint32_t micros() { return ::micros(); }
inline void delay(uint32_t ms) { ::delay(ms); }
inline void delayMicroseconds(uint32_t us) { ::delayMicroseconds(us); }

}  // namespace oc::hal::arduino
```

Créer `hal-arduino/library.json` :
```json
{
  "name": "hal-arduino",
  "version": "0.1.0",
  "description": "Generic Arduino HAL for Open Control",
  "repository": {
    "type": "git",
    "url": "https://github.com/open-control/hal-arduino.git"
  },
  "frameworks": ["arduino"],
  "dependencies": {
    "framework": "*"
  }
}
```

#### 2.5 hal-desktop (nouveau)

```bash
mkdir -p hal-desktop/src/oc/hal/desktop
```

Copier et adapter FileStorageBackend :
```cpp
// hal-desktop/src/oc/hal/desktop/FileStorage.hpp
#pragma once

#include <oc/interface/IStorage.hpp>
#include <cstdio>
#include <cstring>

namespace oc::hal::desktop {

class FileStorage : public oc::IStorage {
public:
    explicit FileStorage(const char* path) : path_(path) {}

    ~FileStorage() override {
        if (file_) fclose(file_);
    }

    bool begin() override {
        file_ = fopen(path_, "r+b");
        if (!file_) {
            file_ = fopen(path_, "w+b");
        }
        return file_ != nullptr;
    }

    bool available() const override { return file_ != nullptr; }

    size_t read(uint32_t address, uint8_t* buffer, size_t size) override {
        if (!file_) return 0;
        fseek(file_, address, SEEK_SET);
        return fread(buffer, 1, size, file_);
    }

    size_t write(uint32_t address, const uint8_t* buffer, size_t size) override {
        if (!file_) return 0;
        fseek(file_, address, SEEK_SET);
        return fwrite(buffer, 1, size, file_);
    }

    bool commit() override {
        if (!file_) return false;
        fflush(file_);
        return true;
    }

    bool erase(uint32_t address, size_t size) override {
        if (!file_) return false;
        std::vector<uint8_t> zeros(size, 0xFF);
        fseek(file_, address, SEEK_SET);
        fwrite(zeros.data(), 1, size, file_);
        return true;
    }

    size_t capacity() const override { return 1024 * 1024; }

private:
    const char* path_;
    FILE* file_ = nullptr;
};

}  // namespace oc::hal::desktop
```

Créer `hal-desktop/library.json` :
```json
{
  "name": "hal-desktop",
  "version": "0.1.0",
  "description": "Desktop HAL for Open Control (POSIX filesystem)",
  "repository": {
    "type": "git",
    "url": "https://github.com/open-control/hal-desktop.git"
  },
  "platforms": ["native"],
  "dependencies": {
    "framework": "*"
  }
}
```

#### 2.6 hal-sdl (mise à jour includes)

```bash
find hal-sdl/src -type f \( -name "*.hpp" -o -name "*.cpp" \) -exec sed -i \
  -e 's|#include <oc/hal/IButtonController\.hpp>|#include <oc/interface/IButton.hpp>|g' \
  -e 's|#include <oc/hal/IEncoderController\.hpp>|#include <oc/interface/IEncoder.hpp>|g' \
  -e 's|#include <oc/hal/IMidiTransport\.hpp>|#include <oc/interface/IMidi.hpp>|g' \
  -e 's|#include <oc/hal/IFrameTransport\.hpp>|#include <oc/interface/ITransport.hpp>|g' \
  -e 's|#include <oc/hal/NullMidiTransport\.hpp>|#include <oc/impl/NullMidi.hpp>|g' \
  -e 's|#include <oc/hal/Types\.hpp>|#include <oc/interface/Types.hpp>|g' \
  -e 's|#include "oc/hal/sdl/|#include "oc/hal/sdl/|g' \
  -e 's|\bIButtonController\b|IButton|g' \
  -e 's|\bIEncoderController\b|IEncoder|g' \
  -e 's|\bIMidiTransport\b|IMidi|g' \
  -e 's|\bIFrameTransport\b|ITransport|g' \
  -e 's|\bNullMidiTransport\b|NullMidi|g' \
  {} \;
```

---

### PHASE 3 : hal-teensy (réorganisation)

**Dépendances** : Phase 1, Phase 2 (hal-common, hal-arduino)
**Validation** : `cd hal-teensy && pio run -e dev`

#### 3.1 Créer les sous-dossiers

```bash
cd /home/simon/petitechose-audio/workspace/open-control/hal-teensy/src/oc/hal/teensy
mkdir -p storage io display hw
mkdir -p /home/simon/petitechose-audio/workspace/open-control/hal-teensy/examples/test
```

#### 3.2 Réorganiser les fichiers

```bash
# Storage
git mv SDCardBackend.hpp storage/
git mv EEPROMBackend.hpp storage/
git mv LittleFSBackend.hpp storage/

# I/O
git mv UsbMidi.hpp io/
git mv UsbMidi.cpp io/
git mv UsbSerial.hpp io/

# Display
git mv Ili9341.hpp display/
git mv Ili9341.cpp display/

# Hardware
git mv ButtonController.hpp hw/
git mv EncoderController.hpp hw/
git mv EncoderToolHardware.hpp hw/
git mv GenericMux.hpp hw/

# Supprimer TeensyGpio (remplacé par hal-arduino)
rm TeensyGpio.hpp

# Supprimer dossier flash vide
rmdir flash 2>/dev/null || true

# Déplacer main.cpp vers examples
cd /home/simon/petitechose-audio/workspace/open-control/hal-teensy
git mv src/main.cpp examples/test/main.cpp
```

#### 3.3 Mettre à jour les includes

```bash
cd /home/simon/petitechose-audio/workspace/open-control

find hal-teensy/src -type f \( -name "*.hpp" -o -name "*.cpp" \) -exec sed -i \
  -e 's|#include <oc/hal/IButtonController\.hpp>|#include <oc/interface/IButton.hpp>|g' \
  -e 's|#include <oc/hal/IDisplayDriver\.hpp>|#include <oc/interface/IDisplay.hpp>|g' \
  -e 's|#include <oc/hal/IEncoderController\.hpp>|#include <oc/interface/IEncoder.hpp>|g' \
  -e 's|#include <oc/hal/IEncoderHardware\.hpp>|#include <oc/interface/IEncoderHardware.hpp>|g' \
  -e 's|#include <oc/hal/IFrameTransport\.hpp>|#include <oc/interface/ITransport.hpp>|g' \
  -e 's|#include <oc/hal/IGpio\.hpp>|#include <oc/interface/IGpio.hpp>|g' \
  -e 's|#include <oc/hal/IMidiTransport\.hpp>|#include <oc/interface/IMidi.hpp>|g' \
  -e 's|#include <oc/hal/IMultiplexer\.hpp>|#include <oc/interface/IMultiplexer.hpp>|g' \
  -e 's|#include <oc/hal/IStorageBackend\.hpp>|#include <oc/interface/IStorage.hpp>|g' \
  -e 's|#include <oc/hal/embedded/|#include <oc/hal/common/embedded/|g' \
  -e 's|#include <oc/hal/teensy/TeensyGpio\.hpp>|#include <oc/hal/arduino/ArduinoGpio.hpp>|g' \
  -e 's|#include <oc/hal/teensy/SDCardBackend\.hpp>|#include <oc/hal/teensy/storage/SDCardBackend.hpp>|g' \
  -e 's|#include <oc/hal/teensy/EEPROMBackend\.hpp>|#include <oc/hal/teensy/storage/EEPROMBackend.hpp>|g' \
  -e 's|#include <oc/hal/teensy/LittleFSBackend\.hpp>|#include <oc/hal/teensy/storage/LittleFSBackend.hpp>|g' \
  -e 's|#include <oc/hal/teensy/UsbMidi\.hpp>|#include <oc/hal/teensy/io/UsbMidi.hpp>|g' \
  -e 's|#include <oc/hal/teensy/UsbSerial\.hpp>|#include <oc/hal/teensy/io/UsbSerial.hpp>|g' \
  -e 's|#include <oc/hal/teensy/Ili9341\.hpp>|#include <oc/hal/teensy/display/Ili9341.hpp>|g' \
  -e 's|#include <oc/hal/teensy/ButtonController\.hpp>|#include <oc/hal/teensy/hw/ButtonController.hpp>|g' \
  -e 's|#include <oc/hal/teensy/EncoderController\.hpp>|#include <oc/hal/teensy/hw/EncoderController.hpp>|g' \
  -e 's|#include <oc/hal/teensy/EncoderToolHardware\.hpp>|#include <oc/hal/teensy/hw/EncoderToolHardware.hpp>|g' \
  -e 's|#include <oc/hal/teensy/GenericMux\.hpp>|#include <oc/hal/teensy/hw/GenericMux.hpp>|g' \
  -e 's|\bIButtonController\b|IButton|g' \
  -e 's|\bIDisplayDriver\b|IDisplay|g' \
  -e 's|\bIEncoderController\b|IEncoder|g' \
  -e 's|\bIFrameTransport\b|ITransport|g' \
  -e 's|\bIMidiTransport\b|IMidi|g' \
  -e 's|\bIStorageBackend\b|IStorage|g' \
  -e 's|TeensyGpio|oc::hal::arduino::ArduinoGpio|g' \
  {} \;
```

#### 3.4 Mettre à jour Teensy.hpp pour utiliser hal-arduino

Modifier manuellement `Teensy.hpp` pour remplacer :
```cpp
#include <oc/hal/teensy/TeensyGpio.hpp>
```
par :
```cpp
#include <oc/hal/arduino/ArduinoGpio.hpp>
```

Et adapter le code qui utilise `TeensyGpio` pour utiliser `oc::hal::arduino::ArduinoGpio`.

#### 3.5 Mettre à jour library.json et platformio.ini

`hal-teensy/library.json` (FUSIONNER avec l'existant, conserver les dépendances externes) :
```json
{
  "name": "hal-teensy",
  "version": "0.2.0",
  "description": "Teensy HAL drivers for Open Control",
  "keywords": ["open-control", "teensy", "hal", "embedded"],
  "repository": {
    "type": "git",
    "url": "https://github.com/open-control/hal-teensy.git"
  },
  "license": "MIT",
  "frameworks": "arduino",
  "platforms": ["teensy"],
  "dependencies": {
    "framework": "https://github.com/open-control/framework.git",
    "hal-common": "https://github.com/open-control/hal-common.git",
    "hal-arduino": "https://github.com/open-control/hal-arduino.git",
    "luni64/EncoderTool": "^3.2.0",
    "vindar/ILI9341_T4": "^1.6.0"
  },
  "build": {
    "includeDir": "src",
    "srcFilter": [
      "+<**/*.cpp>",
      "-<main.cpp>"
    ]
  }
}
```

`hal-teensy/platformio.ini` (REMPLACER intégralement) :
```ini
; Open Control - Teensy HAL Drivers

[platformio]
default_envs = dev

[env]
platform = teensy
board = teensy41
framework = arduino
build_flags = -std=gnu++17 -I src -D USB_MIDI_SERIAL

[env:dev]
lib_deps =
    open-control=symlink://../framework
    hal-common=symlink://../hal-common
    hal-arduino=symlink://../hal-arduino
    https://github.com/luni64/EncoderTool
    https://github.com/vindar/ILI9341_T4
    https://github.com/PaulStoffregen/Encoder

[env:release]
lib_deps =
    https://github.com/open-control/framework
    https://github.com/open-control/hal-common
    https://github.com/open-control/hal-arduino
    https://github.com/luni64/EncoderTool
    https://github.com/vindar/ILI9341_T4
    https://github.com/PaulStoffregen/Encoder
```

---

### PHASE 4 : ui-lvgl (réorganisation)

**Dépendances** : Phase 1
**Validation** : Vérification syntaxique

```bash
cd /home/simon/petitechose-audio/workspace/open-control/ui-lvgl/src/oc/ui/lvgl

mkdir -p interface bridge font
mkdir -p /home/simon/petitechose-audio/workspace/open-control/ui-lvgl/examples/demo

# Interfaces
git mv IComponent.hpp interface/
git mv IElement.hpp interface/
git mv IListItem.hpp interface/
git mv IView.hpp interface/
git mv IWidget.hpp interface/

# Bridge
git mv Bridge.hpp bridge/
git mv Bridge.cpp bridge/
git mv SdlBridge.hpp bridge/
git mv SdlBridge.cpp bridge/

# Font
git mv FontLoader.hpp font/
git mv FontLoader.cpp font/
git mv FontUtils.hpp font/
git mv FontUtils.cpp font/

# main.cpp
cd /home/simon/petitechose-audio/workspace/open-control/ui-lvgl
git mv src/main.cpp examples/demo/main.cpp

# Update includes
find src -type f \( -name "*.hpp" -o -name "*.cpp" \) -exec sed -i \
  -e 's|#include <oc/hal/IDisplayDriver\.hpp>|#include <oc/interface/IDisplay.hpp>|g' \
  -e 's|#include <oc/hal/Types\.hpp>|#include <oc/interface/Types.hpp>|g' \
  -e 's|\bIDisplayDriver\b|IDisplay|g' \
  {} \;
```

---

### PHASE 5 : Examples open-control

**Dépendances** : Phase 3 (hal-teensy)
**Validation** : `cd example-teensy41-minimal && pio run -e dev`

```bash
cd /home/simon/petitechose-audio/workspace/open-control

# IMPORTANT: Les examples utilisent actuellement oc/hal/common/ (sans embedded/)
# mais la structure cible est oc/hal/common/embedded/
# Il faut donc corriger DEUX patterns :
#   1. oc/hal/embedded/     → oc/hal/common/embedded/  (hal-teensy interne)
#   2. oc/hal/common/X      → oc/hal/common/embedded/X (examples cassés)

find example-teensy41-* -type f \( -name "*.hpp" -o -name "*.cpp" \) -exec sed -i \
  -e 's|#include <oc/hal/teensy/Teensy\.hpp>|#include <oc/hal/teensy/Teensy.hpp>|g' \
  -e 's|#include <oc/hal/teensy/UsbMidi\.hpp>|#include <oc/hal/teensy/io/UsbMidi.hpp>|g' \
  -e 's|#include <oc/hal/teensy/Ili9341\.hpp>|#include <oc/hal/teensy/display/Ili9341.hpp>|g' \
  -e 's|#include <oc/hal/Types\.hpp>|#include <oc/interface/Types.hpp>|g' \
  -e 's|#include <oc/context/IContext\.hpp>|#include <oc/interface/IContext.hpp>|g' \
  -e 's|#include <oc/hal/embedded/|#include <oc/hal/common/embedded/|g' \
  -e 's|#include <oc/hal/common/ButtonDef|#include <oc/hal/common/embedded/ButtonDef|g' \
  -e 's|#include <oc/hal/common/EncoderDef|#include <oc/hal/common/embedded/EncoderDef|g' \
  -e 's|#include <oc/hal/common/GpioPin|#include <oc/hal/common/embedded/GpioPin|g' \
  -e 's|#include <oc/hal/common/Types|#include <oc/hal/common/embedded/Types|g' \
  -e 's|oc::hal::common::ButtonDef|oc::hal::common::embedded::ButtonDef|g' \
  -e 's|oc::hal::common::EncoderDef|oc::hal::common::embedded::EncoderDef|g' \
  -e 's|oc::hal::common::GpioPin|oc::hal::common::embedded::GpioPin|g' \
  {} \;

# Mettre à jour platformio.ini pour utiliser hal-common au lieu de hal-embedded
find example-teensy41-* -name "platformio.ini" -exec sed -i \
  -e 's|hal-embedded|hal-common|g' \
  {} \;
```

---

### PHASE 6 : protocol-codegen

**Dépendances** : Phase 1
**Validation** : `grep -rn "IFrameTransport\|oc/hal/I" protocol-codegen/` doit être vide

#### 6.1 Fichiers à modifier

| Fichier | Lignes | Modification |
|---------|--------|--------------|
| `framing.py` | 56 | `"oc::hal::IFrameTransport"` → `"oc::ITransport"` |
| `framing.py` | 57 | `"IFrameTransport"` → `"ITransport"` |
| `framing.py` | 124 | `'#include <oc/hal/IFrameTransport.hpp>\n'` → `'#include <oc/interface/ITransport.hpp>\n'` |
| `protocol_generator.py` | 67, 103, 124, 126, 181, 228 | Remplacer toutes les références |

#### 6.2 Script de mise à jour

```bash
cd /home/simon/petitechose-audio/workspace/open-control/protocol-codegen

# framing.py - 3 modifications
sed -i \
  -e 's|"oc::hal::IFrameTransport"|"oc::ITransport"|g' \
  -e 's|"IFrameTransport"|"ITransport"|g' \
  -e "s|#include <oc/hal/IFrameTransport.hpp>|#include <oc/interface/ITransport.hpp>|g" \
  src/protocol_codegen/generators/protocols/binary/framing.py

# protocol_generator.py - 6 modifications (lignes 67, 103, 124, 126, 181, 228)
sed -i \
  -e 's|oc::hal::IFrameTransport|oc::ITransport|g' \
  -e 's|oc/hal/IFrameTransport\.hpp|oc/interface/ITransport.hpp|g' \
  -e 's|IFrameTransport|ITransport|g' \
  src/protocol_codegen/generators/binary/cpp/protocol_generator.py

# Vérification : aucune référence ne doit rester
echo "=== Vérification ==="
grep -rn "IFrameTransport" src/ && echo "ERREUR: références restantes" || echo "OK: aucune référence IFrameTransport"
grep -rn "oc/hal/I" src/ && echo "ERREUR: anciens includes" || echo "OK: aucun ancien include"
```

#### 6.3 Régénérer le code exemple (optionnel)

```bash
# Si un protocole existe, régénérer pour vérifier
cd examples/simple-sensor-network
./generate.sh
grep -n "ITransport\|IFrameTransport" generated/*.hpp
# Doit afficher ITransport, pas IFrameTransport
```

---

### PHASE 7 : Documentation open-control

**Dépendances** : Toutes les phases précédentes
**Validation** : `grep -rn "oc/hal/" --include="*.md" open-control/` doit retourner uniquement hal-teensy, hal-sdl, hal-arduino, hal-desktop, hal-common

#### 7.1 framework/README.md

Mettre à jour les exemples et liens.

#### 7.2 hal-teensy/README.md

Mettre à jour les exemples et liens.

#### 7.3 example-*/README.md

Mettre à jour les instructions de clonage.

#### 7.4 ui-lvgl-components/README.md

Mettre à jour les liens vers hal-common.

#### 7.5 .github/profile/README.md

Déjà correct (utilise hal-common).

#### 7.6 example-00-architecture/CHEATSHEET.md

Mettre à jour les exemples de code.

---

### PHASE 8 : Opérations Git

**Dépendances** : Toutes les phases code terminées
**Validation** : `git remote -v` dans chaque repo

#### 8.1 Renommer les repos sur GitHub

Via GitHub Settings → General → Repository name :
1. `open-control/hal-embedded` → `open-control/hal-common`
2. `open-control/hal-midi` → `open-control/transport-midi`
3. `open-control/hal-net` → `open-control/transport-net`

#### 8.2 Créer les nouveaux repos sur GitHub

Via GitHub :
1. Créer `open-control/hal-arduino`
2. Créer `open-control/hal-desktop`

#### 8.3 Mettre à jour les remotes locaux

```bash
cd /home/simon/petitechose-audio/workspace/open-control

# hal-common (anciennement hal-embedded)
cd hal-common
git remote set-url origin https://github.com/open-control/hal-common.git
cd ..

# transport-midi (anciennement hal-midi)
cd transport-midi
git remote set-url origin https://github.com/open-control/transport-midi.git
cd ..

# transport-net (anciennement hal-net)
cd transport-net
git remote set-url origin https://github.com/open-control/transport-net.git
cd ..

# hal-arduino (nouveau)
cd hal-arduino
git init
git remote add origin https://github.com/open-control/hal-arduino.git
cd ..

# hal-desktop (nouveau)
cd hal-desktop
git init
git remote add origin https://github.com/open-control/hal-desktop.git
cd ..
```

#### 8.4 Commit et push

```bash
# Pour chaque repo modifié
git add -A
git commit -m "refactor: architecture migration v2

- Move interfaces to framework/interface/
- Move implementations to framework/impl/
- Rename classes (IButtonController → IButton, etc.)
- Update all includes and namespaces

Co-Authored-By: Claude <noreply@anthropic.com>"

git push origin main
```

---

### PHASE 9 : midi-studio (SÉPARÉ)

**À faire dans un second temps**, après validation complète de open-control.

Fichiers à mettre à jour :
- `core/main.cpp`
- `core/src/state/CoreState.hpp`
- `core/src/state/CoreSettings.hpp`
- `core/src/handler/transport/TransportHandler.cpp`
- `core/src/config/platform-teensy/Hardware.hpp`
- `core/src/config/platform-teensy/HardwareDisplay.hpp`
- `core/src/config/InputIDs.hpp`
- `core/sdl/main-native.cpp`
- `core/sdl/main-wasm.cpp`
- `core/sdl/MemoryStorage.hpp` (supprimer, utiliser oc/impl/MemoryStorage.hpp)
- `core/sdl/SdlEnvironment.cpp`
- `core/sdl/HwSimulator.cpp`
- `plugin-bitwig/src/main.cpp`
- `plugin-bitwig/sdl/main-native.cpp`
- `plugin-bitwig/sdl/main-wasm.cpp`
- `plugin-bitwig/src/protocol/BitwigProtocol.hpp`

---

## Tracking

### Checklist des phases

- [ ] **Phase 1** : Framework
  - [ ] 1.1 Créer dossiers
  - [ ] 1.2-1.4 Déplacer fichiers
  - [ ] 1.5-1.6 Créer impl/
  - [ ] 1.7-1.8 Renommer classes
  - [ ] 1.9 Mettre à jour includes
  - [ ] 1.10 Supprimer hal/
  - [ ] **Validation** : `pio run -e native`

- [ ] **Phase 2** : HALs
  - [ ] 2.1 hal-common
  - [ ] 2.2 transport-midi
  - [ ] 2.3 transport-net
  - [ ] 2.4 hal-arduino
  - [ ] 2.5 hal-desktop
  - [ ] 2.6 hal-sdl
  - [ ] **Validation** : grep namespaces

- [ ] **Phase 3** : hal-teensy
  - [ ] 3.1-3.2 Réorganiser
  - [ ] 3.3-3.4 Mettre à jour includes
  - [ ] 3.5 library.json + platformio.ini
  - [ ] **Validation** : `pio run -e dev`

- [ ] **Phase 4** : ui-lvgl
  - [ ] Réorganiser + includes
  - [ ] **Validation** : syntaxe

- [ ] **Phase 5** : Examples
  - [ ] Mettre à jour includes
  - [ ] Mettre à jour platformio.ini
  - [ ] **Validation** : `pio run -e dev`

- [ ] **Phase 6** : protocol-codegen
  - [ ] Mettre à jour templates
  - [ ] **Validation** : régénérer code

- [ ] **Phase 7** : Documentation
  - [ ] READMEs
  - [ ] CHEATSHEET
  - [ ] **Validation** : grep anciens paths

- [ ] **Phase 8** : Git
  - [ ] Renommer repos GitHub
  - [ ] Créer nouveaux repos
  - [ ] Mettre à jour remotes
  - [ ] Push

- [ ] **Phase 9** : midi-studio (SÉPARÉ)

---

## Vérifications finales

```bash
cd /home/simon/petitechose-audio/workspace/open-control

# Aucun ancien include ne doit rester (sauf dans docs/)
grep -rn "oc/hal/I" --include="*.hpp" --include="*.cpp" .
# Attendu: vide

# Aucun ancien namespace
grep -rn "oc::hal::embedded" --include="*.hpp" .
# Attendu: vide

# Aucune ancienne classe
grep -rn "IButtonController\|IDisplayDriver\|IEncoderController\|IStorageBackend\|IMidiTransport\|IFrameTransport" --include="*.hpp" --include="*.cpp" .
# Attendu: vide

# Aucun ancien path oc/hal/common (sans embedded)
grep -rn "oc/hal/common/" --include="*.hpp" --include="*.cpp" . | grep -v "oc/hal/common/embedded"
# Attendu: vide
```
