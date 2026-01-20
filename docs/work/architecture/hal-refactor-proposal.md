# Proposition: Refactoring Architecture HAL

**Status**: Draft - À valider
**Created**: 2026-01-20
**Context**: Clarification de l'architecture open-control pour supporter multi-plateforme

---

## Problème actuel

Le dossier `hal/` mélange :
- Interfaces abstraites (`IStorage`, `IDisplay`...)
- Types communs
- Implémentations nulles (`NullMidiTransport`)

Pas de place claire pour les implémentations portables (standard C++ comme `FileStorage`).

---

## Inspirations (projets open source)

| Projet | Pattern clé | Lien |
|--------|-------------|------|
| **Rust embedded-hal** | Traits séparés des implémentations | [GitHub](https://github.com/rust-embedded/embedded-hal) |
| **Mbed OS** | Couches empilées (App → API → HAL → Vendor) | [Docs](https://os.mbed.com/docs/mbed-os/v6.16/introduction/architecture.html) |
| **ESP-IDF** | 3 niveaux : LL → HAL → Driver | [Docs](https://docs.espressif.com/projects/esp-idf/en/stable/esp32/api-guides/hardware-abstraction.html) |
| **Zephyr RTOS** | HALs vendeurs externes, drivers génériques | [DeepWiki](https://deepwiki.com/zephyrproject-rtos/zephyr/3.2-board-support-and-hardware-abstraction) |

### Principes retenus

1. **Interface/Impl séparés** - Interfaces dans un endroit, implémentations ailleurs
2. **Portable vs Platform** - Code standard C++ séparé du code plateforme
3. **HAL par vendeur/plateforme** - Un module par cible (Teensy, STM32, SDL...)
4. **API stable en haut** - L'application ne voit que les interfaces

---

## Architecture proposée

### Vue d'ensemble

```
framework/src/oc/
├── interface/          ← Interfaces abstraites (contrats)
├── portable/           ← Implémentations standard C++ (fopen, vector...)
├── core/               ← Types de base, Result, events...
├── state/              ← State management (Signal, Settings...)
├── app/                ← Application framework
├── api/                ← APIs haut niveau (EncoderAPI, ButtonAPI...)
├── context/            ← Gestion des contextes
└── ...

hal-teensy/             ← Implémentations Teensy 4.x
hal-stm32/              ← Implémentations STM32 (futur)
hal-sdl/                ← Simulateur desktop (SDL2)
hal-embedded/           ← Code partagé entre MCUs
hal-midi/               ← MIDI portable (libremidi)
```

### Détail `interface/`

Contient **uniquement** les interfaces abstraites. Aucune dépendance plateforme.

```cpp
// interface/IStorage.hpp
class IStorage {
public:
    virtual ~IStorage() = default;
    virtual bool begin() = 0;
    virtual size_t read(uint32_t addr, uint8_t* buf, size_t size) = 0;
    virtual size_t write(uint32_t addr, const uint8_t* buf, size_t size) = 0;
    virtual bool commit() = 0;
    // ...
};
```

**Fichiers :**
```
interface/
├── IStorage.hpp        ← Stockage persistant
├── IDisplay.hpp        ← Affichage
├── IEncoder.hpp        ← Contrôleur encodeurs
├── IEncoderHardware.hpp← Hardware encodeur (interrupts)
├── IButton.hpp         ← Contrôleur boutons
├── IGpio.hpp           ← GPIO abstrait
├── IMidi.hpp           ← Transport MIDI
├── ITransport.hpp      ← Transport frames/serial
├── IMultiplexer.hpp    ← Multiplexeur analogique
└── Types.hpp           ← Types communs (ButtonState, etc.)
```

### Détail `portable/`

Implémentations utilisant **uniquement** le standard C++ (fopen, vector, etc.).
Fonctionne sur toutes les plateformes (Native, WASM, et même embedded si stdlib dispo).

```cpp
// portable/FileStorage.hpp
class FileStorage : public IStorage {
public:
    explicit FileStorage(const char* path);
    bool begin() override;
    size_t read(...) override;  // fseek + fread
    size_t write(...) override; // fseek + fwrite
    bool commit() override;     // fflush
private:
    FILE* file_;
};
```

**Fichiers :**
```
portable/
├── FileStorage.hpp     ← Stockage fichier (fopen/fwrite)
├── MemoryStorage.hpp   ← Stockage RAM (pour tests)
└── NullMidi.hpp        ← MIDI no-op
```

### Détail `hal-teensy/`

Implémentations spécifiques Teensy 4.x. Dépend des libs Arduino/Teensy.

```
hal-teensy/src/oc/hal/teensy/
├── storage/
│   ├── SDCardStorage.hpp       ← SD card via SDIO
│   ├── EEPROMStorage.hpp       ← EEPROM émulée
│   └── LittleFSStorage.hpp     ← Flash interne
├── io/
│   ├── UsbMidi.hpp             ← USB MIDI natif
│   └── UsbSerial.hpp           ← USB Serial
├── display/
│   └── Ili9341.hpp             ← Écran ILI9341 SPI
├── hw/
│   ├── TeensyGpio.hpp          ← GPIO Teensy
│   ├── EncoderController.hpp   ← Gestion encodeurs
│   ├── EncoderToolHardware.hpp ← Interrupts encodeurs
│   ├── ButtonController.hpp    ← Gestion boutons
│   └── GenericMux.hpp          ← Multiplexeur CD74HC4067
├── AppBuilder.hpp              ← Builder pattern pour app
├── Teensy.hpp                  ← Includes communs
└── TeensyOutput.hpp            ← Output helpers
```

### Détail `hal-sdl/`

Simulateur desktop utilisant SDL2. Pour développement sans hardware.

```
hal-sdl/src/oc/hal/sdl/
├── input/
│   ├── SdlButtonController.hpp   ← Boutons simulés (clavier)
│   ├── SdlEncoderController.hpp  ← Encodeurs simulés (souris)
│   └── InputMapper.hpp           ← Mapping clavier/souris
├── AppBuilder.hpp
├── Sdl.hpp
├── SdlOutput.hpp
└── SdlTime.hpp
```

### Détail `hal-embedded/`

Code partagé entre différents MCUs (Teensy, STM32, etc.).

```
hal-embedded/src/oc/hal/embedded/
├── ButtonDef.hpp       ← Structure définition bouton
├── EncoderDef.hpp      ← Structure définition encodeur
├── GpioPin.hpp         ← Abstraction pin GPIO
└── Types.hpp           ← Types embarqués communs
```

### Détail `hal-midi/`

MIDI portable via libremidi. Séparé car dépendance externe optionnelle.

```
hal-midi/src/oc/hal/midi/
└── LibreMidiTransport.hpp  ← Impl IMidi avec libremidi
```

---

## Mapping fichiers actuels → nouveaux

### framework/src/oc/hal/ → Split

| Actuel | Nouveau | Type |
|--------|---------|------|
| `IStorageBackend.hpp` | `interface/IStorage.hpp` | Interface |
| `IDisplayDriver.hpp` | `interface/IDisplay.hpp` | Interface |
| `IEncoderController.hpp` | `interface/IEncoder.hpp` | Interface |
| `IEncoderHardware.hpp` | `interface/IEncoderHardware.hpp` | Interface |
| `IButtonController.hpp` | `interface/IButton.hpp` | Interface |
| `IGpio.hpp` | `interface/IGpio.hpp` | Interface |
| `IMultiplexer.hpp` | `interface/IMultiplexer.hpp` | Interface |
| `IMidiTransport.hpp` | `interface/IMidi.hpp` | Interface |
| `IFrameTransport.hpp` | `interface/ITransport.hpp` | Interface |
| `NullMidiTransport.hpp` | `portable/NullMidi.hpp` | Portable |
| `Types.hpp` | `interface/Types.hpp` | Types |

### hal-teensy/ → Réorganisation

| Actuel | Nouveau |
|--------|---------|
| `SDCardBackend.hpp` | `storage/SDCardStorage.hpp` |
| `EEPROMBackend.hpp` | `storage/EEPROMStorage.hpp` |
| `LittleFSBackend.hpp` | `storage/LittleFSStorage.hpp` |
| `UsbMidi.hpp` | `io/UsbMidi.hpp` |
| `UsbSerial.hpp` | `io/UsbSerial.hpp` |
| `Ili9341.hpp` | `display/Ili9341.hpp` |
| `TeensyGpio.hpp` | `hw/TeensyGpio.hpp` |
| `EncoderController.hpp` | `hw/EncoderController.hpp` |
| `ButtonController.hpp` | `hw/ButtonController.hpp` |
| `GenericMux.hpp` | `hw/GenericMux.hpp` |

---

## Conventions de nommage

| Type | Convention | Exemple |
|------|------------|---------|
| Interface | Préfixe `I` | `IStorage`, `IDisplay` |
| Implémentation portable | Nom descriptif | `FileStorage`, `MemoryStorage` |
| Implémentation plateforme | Préfixe plateforme ou nom hardware | `SDCardStorage`, `Ili9341` |
| Types/Enums | PascalCase | `ButtonState`, `EncoderEvent` |

---

## Includes après refactoring

```cpp
// Interfaces
#include <oc/interface/IStorage.hpp>
#include <oc/interface/IMidi.hpp>

// Implémentations portables
#include <oc/portable/FileStorage.hpp>
#include <oc/portable/MemoryStorage.hpp>

// Implémentations Teensy
#include <oc/hal/teensy/storage/SDCardStorage.hpp>
#include <oc/hal/teensy/io/UsbMidi.hpp>

// Implémentations SDL
#include <oc/hal/sdl/input/SdlEncoderController.hpp>
```

---

## Plan d'implémentation

| Phase | Tâche | Effort |
|-------|-------|--------|
| 1 | Créer `interface/` + déplacer I*.hpp | 30min |
| 2 | Créer `portable/` + FileStorage + MemoryStorage | 1h |
| 3 | Réorganiser hal-teensy/ en sous-dossiers | 30min |
| 4 | Réorganiser hal-sdl/ en sous-dossiers | 15min |
| 5 | Mettre à jour tous les imports | 2-3h |
| 6 | Tests compilation tous les projets | 1h |
| **Total** | | **~5-6h** |

---

## Questions ouvertes

1. **Nommage `interface/` vs `api/`** - Conflit avec `api/` existant (EncoderAPI...) ?
2. **hal-midi reste séparé ?** - Ou intégrer dans `portable/` ?
3. **Rétrocompatibilité** - Fournir des includes de compatibilité temporaires ?

---

## Décision

- [ ] Approuvé - Implémenter
- [ ] Modifié - Voir commentaires
- [ ] Reporté - Pas prioritaire maintenant
