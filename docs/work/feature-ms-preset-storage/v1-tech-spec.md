# V1 Tech Spec: Preset Storage System

**Version**: 2.0
**Date**: 2026-01-20
**Status**: Implémenté (storage backends)

---

## Résumé

Persistence des presets sur toutes les plateformes avec des backends adaptés.

| Plateforme | Backend | Persistence | Status |
|------------|---------|-------------|--------|
| Teensy 4.1 | SDCardBackend | SD card SDIO | ✅ Implémenté |
| Native | FileStorageBackend | Fichier local | ✅ Implémenté |
| WASM | MemoryStorage | RAM (preview) | ✅ Implémenté |

**Décision clé** : LittleFS abandonné car bloque FlexSPI (~300ms freeze UI). SD card via SDIO est non-bloquant.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     CODE APPLICATIF                         │
│                                                             │
│  CoreState ──► CoreSettings ──► IStorageBackend             │
└─────────────────────────────────────────────────────────────┘
                          │
          ┌───────────────┼───────────────┐
          ▼               ▼               ▼
     ┌──────────┐    ┌──────────┐    ┌──────────┐
     │ TEENSY   │    │  NATIVE  │    │   WASM   │
     ├──────────┤    ├──────────┤    ├──────────┤
     │SDCard    │    │  File    │    │ Memory   │
     │Backend   │    │ Storage  │    │ Storage  │
     │(SDIO)    │    │ Backend  │    │ (RAM)    │
     └──────────┘    └──────────┘    └──────────┘
          │               │               │
          ▼               ▼               ▼
     /macros.bin    ./macros.bin    (volatile)
```

---

## Backends implémentés

### 1. SDCardBackend (Teensy)

**Fichier** : `hal-teensy/src/oc/hal/teensy/SDCardBackend.hpp`

```cpp
class SDCardBackend : public IStorageBackend {
    explicit SDCardBackend(const char* filename, size_t capacity = 1024*1024);
    bool begin() override;           // SD.begin() + open file
    bool available() const override; // SD.mediaPresent()
    size_t read(...) override;       // seek + fread
    size_t write(...) override;      // seek + fwrite (extend with 0xFF)
    bool commit() override;          // fflush
    bool erase(...) override;        // write 0xFF
    size_t capacity() const override;
};
```

**Caractéristiques** :
- Bus SDIO séparé de FlexSPI → non-bloquant
- Handle fichier persistant (évite open/close)
- Padding statique 64 bytes (zero allocation)

### 2. FileStorageBackend (Native)

**Fichier** : `framework/src/oc/hal/FileStorageBackend.hpp`

```cpp
class FileStorageBackend : public IStorageBackend {
    explicit FileStorageBackend(const char* path, size_t capacity = 64*1024);
    // Mêmes méthodes, implémentation via fopen/fwrite standard C++
};
```

**Caractéristiques** :
- Standard C++ (fopen, fwrite, fseek)
- Handle persistant
- Fonctionne sur Linux/macOS/Windows

### 3. MemoryStorage (WASM)

**Fichier** : `midi-studio/core/sdl/MemoryStorage.hpp`

```cpp
class MemoryStorage : public IStorageBackend {
    explicit MemoryStorage(size_t capacity = 4096);
    // Stockage en RAM via std::vector<uint8_t>
};
```

**Caractéristiques** :
- Preview mode uniquement
- Données perdues au refresh
- Persistence future via bridge REST API

---

## Intégration

### main.cpp (Teensy)

```cpp
static oc::hal::teensy::SDCardBackend storage("/macros.bin");

void setup() {
    if (!storage.begin()) {
        OC_LOG_ERROR("Storage init failed!");
        while (true) {}
    }
    coreState.emplace(storage);
}
```

### main-native.cpp

```cpp
oc::hal::FileStorageBackend storage("./macros.bin");
if (!storage.begin()) {
    return 1;
}
core::state::CoreState coreState(storage);
```

### main-wasm.cpp

```cpp
desktop::MemoryStorage storage;
storage.begin();
core::state::CoreState coreState(storage);
// Persistence via bridge REST API (V2)
```

---

## Format de stockage

Layout CoreSettings (528 bytes) :

| Offset | Size | Content |
|--------|------|---------|
| 0x0000 | 4 | Magic "MCST" (0x4D435354) |
| 0x0004 | 1 | Version |
| 0x0005 | 1 | Active page index |
| 0x0006 | 10 | Reserved |
| 0x0010 | 512 | 8 pages × 64 bytes |

---

## V2 Roadmap

### Persistence WASM via Bridge

```
WASM App ──WebSocket──► Bridge ──REST──► Filesystem
                           │
                    GET/POST /storage
                           │
                    ~/.config/midi-studio/
```

### Conversion JSON ↔ Binaire

Pour export/import de presets lisibles :

```
Controller (binary) ◄──► Bridge (convert) ◄──► Web GUI (JSON)
```

---

## Tests

```bash
# Build et test Native
ms build core native
ms run core
# Vérifier ./macros.bin créé (528 bytes)

# Build WASM
ms build core wasm
ms web core
# Preview mode, pas de persistence
```

---

## Fichiers modifiés

| Fichier | Action |
|---------|--------|
| `framework/src/oc/hal/FileStorageBackend.hpp` | ✅ Créé |
| `framework/src/oc/hal/IStorageBackend.hpp` | ✅ Existant |
| `hal-teensy/src/oc/hal/teensy/SDCardBackend.hpp` | ✅ Créé |
| `midi-studio/core/sdl/MemoryStorage.hpp` | ✅ Modifié (begin()) |
| `midi-studio/core/sdl/main-native.cpp` | ✅ Modifié |
| `midi-studio/core/sdl/main-wasm.cpp` | ✅ Modifié |
| `commands/ms` | ✅ Modifié (check deps) |
