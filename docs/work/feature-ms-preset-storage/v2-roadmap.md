# V2 Roadmap: Preset Storage Extensions

**Version**: 1.0
**Date**: 2026-01-19
**Status**: Future - après validation V1

---

## Prérequis

- V1 stable et testée sur toutes les plateformes
- Pas de bugs de régression Teensy
- Persistence Native/WASM validée

---

## Vue d'ensemble V2

V2 **étend** V1 sans la casser. Les interfaces V1 restent stables.

```
V1 (inchangé):
┌─────────────────────────────────────────────────────────┐
│  PresetManager → Settings<PresetData> → IStorageBackend │
└─────────────────────────────────────────────────────────┘

V2 (extension):
┌─────────────────────────────────────────────────────────┐
│  PresetManager                                           │
│       │                                                  │
│       ├──► Settings<PresetData>  (V1 - preset actif)    │
│       │                                                  │
│       └──► IPresetBank (V2 - multi-presets)             │
│                 │                                        │
│       ┌─────────┼─────────┐                             │
│       ▼         ▼         ▼                             │
│   FileBank  LittleFSBank  HttpBank                      │
│   (Native)   (Teensy)     (WASM)                        │
└─────────────────────────────────────────────────────────┘
```

---

## Features V2

| Feature | Description | Effort | Dépendances |
|---------|-------------|--------|-------------|
| Multi-presets | Slots 1-99, sauvegarde/chargement | 6-8h | V1 |
| LittleFSPresetBank | Multi-presets sur LittleFS | 3-4h | Multi-presets |
| Bridge HTTP | Routes REST pour WASM | 4-6h | V1 WASM |
| Sync Teensy↔Desktop | Transfert via USB/Serial | 6-8h | Bridge HTTP |
| Noms personnalisés | Nommer les presets | 2-3h | Multi-presets |
| GUI Manager | Interface web gestion | 8-12h | Bridge HTTP |

**Total estimé** : 30-40h

> **Note** : LittleFS single-file storage est en V1 (validé 2026-01-19). V2 ajoute uniquement la gestion multi-presets sur LittleFS.

---

## 1. Multi-presets (IPresetBank)

### Interface

```cpp
// framework/src/oc/hal/IPresetBank.hpp

namespace oc::hal {

struct PresetInfo {
    uint8_t slot;           ///< Slot number (1-99)
    uint8_t pageCount;      ///< Number of pages
    char name[32];          ///< V2: Custom name (empty in V1 migration)
    uint32_t modified;      ///< Unix timestamp last modified
};

/**
 * @brief Interface for multi-preset storage (V2)
 *
 * Manages a collection of presets in separate files/storage areas.
 */
class IPresetBank {
public:
    virtual ~IPresetBank() = default;

    /// Number of saved presets
    virtual size_t count() const = 0;

    /// Check if slot exists
    virtual bool exists(uint8_t slot) const = 0;

    /// Load preset into PresetData
    virtual bool load(uint8_t slot, PresetData& out) = 0;

    /// Save PresetData to slot
    virtual bool save(uint8_t slot, const PresetData& data) = 0;

    /// Create new preset in next free slot
    /// @return slot number, or 0 if full
    virtual uint8_t create(const PresetData& data) = 0;

    /// Delete preset
    virtual bool remove(uint8_t slot) = 0;

    /// List all presets
    virtual void enumerate(std::function<void(const PresetInfo&)> callback) = 0;

    /// Find next free slot (0 if full)
    virtual uint8_t findFreeSlot() const = 0;
};

}  // namespace oc::hal
```

### Implémentation FilePresetBank (Native)

```cpp
// framework/src/oc/hal/FilePresetBank.hpp

namespace oc::hal {

/**
 * @brief File-based preset bank for desktop
 *
 * Stores presets in: ~/.config/midi-studio/core/presets/001.bin, 002.bin, etc.
 */
class FilePresetBank : public IPresetBank {
public:
    explicit FilePresetBank(const std::string& directory);

    size_t count() const override;
    bool exists(uint8_t slot) const override;
    bool load(uint8_t slot, PresetData& out) override;
    bool save(uint8_t slot, const PresetData& data) override;
    uint8_t create(const PresetData& data) override;
    bool remove(uint8_t slot) override;
    void enumerate(std::function<void(const PresetInfo&)> callback) override;
    uint8_t findFreeSlot() const override;

private:
    std::string slotToPath(uint8_t slot) const;
    std::string directory_;
};

}  // namespace oc::hal
```

### Format fichier preset

```
Offset  Size  Content
──────────────────────────────────
0x0000  4     Magic (0x4D535032 "MSP2")
0x0004  1     Version (2)
0x0005  1     pageCount
0x0006  2     reserved
0x0008  32    name (null-terminated)
0x0028  4     modified (unix timestamp)
0x002C  4     checksum (CRC32 of pages)
0x0030  N*64  pages (N = pageCount)
──────────────────────────────────
Total: 48 + N*64 bytes
```

### Extension PresetManager

```cpp
// V2 additions to PresetManager

class PresetManager {
public:
    // ... V1 API inchangée ...

    // ═══════════════════════════════════════════════════════════════════
    // V2: Multi-preset API
    // ═══════════════════════════════════════════════════════════════════

    /// Set preset bank (V2 - called at init if available)
    void setPresetBank(std::unique_ptr<IPresetBank> bank) {
        bank_ = std::move(bank);
    }

    /// Get preset bank (nullptr in V1)
    IPresetBank* getPresetBank() { return bank_.get(); }

    /// Load preset from bank into active
    bool loadFromBank(uint8_t slot) {
        if (!bank_ || !bank_->exists(slot)) return false;
        PresetData loaded;
        if (!bank_->load(slot, loaded)) return false;
        settings_.modify([&](PresetData& d) { d = loaded; });
        currentSlot_ = slot;
        return true;
    }

    /// Save active preset to bank
    bool saveToBank(uint8_t slot) {
        if (!bank_) return false;
        if (!bank_->save(slot, data())) return false;
        currentSlot_ = slot;
        return true;
    }

    /// Create new preset in bank from active
    uint8_t createInBank() {
        if (!bank_) return 0;
        uint8_t slot = bank_->create(data());
        if (slot > 0) currentSlot_ = slot;
        return slot;
    }

    /// Current slot (0 = not from bank)
    uint8_t currentSlot() const { return currentSlot_; }

private:
    std::unique_ptr<IPresetBank> bank_;  // V2: nullptr in V1
    uint8_t currentSlot_ = 0;            // V2: current bank slot
};
```

### Rétrocompatibilité

| Aspect | Stratégie |
|--------|-----------|
| V1 sans bank | `getPresetBank()` retourne `nullptr`, API V1 fonctionne |
| Migration V1→V2 | Premier lancement V2 : copie preset actif vers slot 1 |
| Format fichier | Nouveau magic `MSP2`, V1 ignore ces fichiers |

---

## 2. LittleFSPresetBank (Multi-presets)

### Prérequis

✅ **Validé 2026-01-19** : LittleFS survit aux uploads firmware.

Test effectué dans `midi-studio/tests/littlefs-persistence/` :
- Bootloader >= 1.07 confirmé
- Fichier persiste après re-flash
- 7424KB de flash persistant disponible
- Code < 512KB requis (test: ~60KB)

**Note** : V1 utilise déjà LittleFSBackend pour single-file storage.
V2 étend avec LittleFSPresetBank pour multi-presets (fichiers séparés par slot).

### Implémentation LittleFSPresetBank

```cpp
// hal-teensy/src/oc/hal/teensy/LittleFSPresetBank.hpp

#include <LittleFS.h>

namespace oc::hal::teensy {

class LittleFSPresetBank : public IPresetBank {
public:
    explicit LittleFSPresetBank(size_t fsSize = 512 * 1024)
        : fsSize_(fsSize) {}

    bool init() {
        if (!fs_.begin(fsSize_)) {
            OC_LOG_ERROR("[LittleFSBank] Mount failed");
            return false;
        }

        // Create presets directory
        if (!fs_.exists("/presets")) {
            fs_.mkdir("/presets");
        }

        OC_LOG_INFO("[LittleFSBank] Mounted {}KB", fsSize_ / 1024);
        return true;
    }

    // ... IPresetBank implementation using fs_.open(), etc.

private:
    LittleFS_Program fs_;
    size_t fsSize_;
};

}  // namespace oc::hal::teensy
```

### Intégration main.cpp Teensy

```cpp
// V2 Teensy main.cpp

static oc::hal::teensy::EEPROMBackend storage;
static oc::hal::teensy::LittleFSPresetBank presetBank;  // V2
static std::optional<core::state::PresetManager> presets;

void setup() {
    // ...
    presets.emplace(storage);
    presets->init();

    // V2: Add preset bank
    if (presetBank.init()) {
        presets->setPresetBank(
            std::make_unique<oc::hal::teensy::LittleFSPresetBank>());
    }

    coreState.emplace(*presets);
}
```

---

## 3. Bridge HTTP

### Routes

```
GET    /storage/{app}/presets           → List presets
GET    /storage/{app}/presets/{slot}    → Get preset binary
PUT    /storage/{app}/presets/{slot}    → Save preset binary
DELETE /storage/{app}/presets/{slot}    → Delete preset
```

### Implémentation Rust (bridge)

```rust
// bridge/src/storage.rs

use axum::{
    extract::Path,
    http::StatusCode,
    response::IntoResponse,
    routing::{get, put, delete},
    Router,
    body::Bytes,
};
use std::path::PathBuf;
use tokio::fs;

pub fn routes() -> Router {
    Router::new()
        .route("/storage/:app/presets", get(list_presets))
        .route("/storage/:app/presets/:slot",
               get(get_preset).put(put_preset).delete(delete_preset))
}

fn presets_dir(app: &str) -> PathBuf {
    dirs::config_dir()
        .unwrap_or_else(|| PathBuf::from("."))
        .join("midi-studio")
        .join(app)
        .join("presets")
}

async fn list_presets(Path(app): Path<String>) -> impl IntoResponse {
    let dir = presets_dir(&app);
    let mut presets = Vec::new();

    if let Ok(mut entries) = fs::read_dir(&dir).await {
        while let Ok(Some(entry)) = entries.next_entry().await {
            if let Some(name) = entry.file_name().to_str() {
                if let Some(slot) = name.strip_suffix(".bin")
                    .and_then(|s| s.parse::<u8>().ok())
                {
                    presets.push(serde_json::json!({"slot": slot}));
                }
            }
        }
    }

    axum::Json(presets)
}

async fn get_preset(Path((app, slot)): Path<(String, u8)>) -> impl IntoResponse {
    let path = presets_dir(&app).join(format!("{:03}.bin", slot));
    match fs::read(&path).await {
        Ok(data) => (StatusCode::OK, data).into_response(),
        Err(_) => StatusCode::NOT_FOUND.into_response(),
    }
}

async fn put_preset(
    Path((app, slot)): Path<(String, u8)>,
    body: Bytes
) -> StatusCode {
    let dir = presets_dir(&app);
    fs::create_dir_all(&dir).await.ok();

    let path = dir.join(format!("{:03}.bin", slot));
    match fs::write(&path, &body).await {
        Ok(_) => StatusCode::OK,
        Err(_) => StatusCode::INTERNAL_SERVER_ERROR,
    }
}

async fn delete_preset(Path((app, slot)): Path<(String, u8)>) -> StatusCode {
    let path = presets_dir(&app).join(format!("{:03}.bin", slot));
    match fs::remove_file(&path).await {
        Ok(_) => StatusCode::OK,
        Err(_) => StatusCode::NOT_FOUND,
    }
}
```

### Cargo.toml additions

```toml
[dependencies]
axum = "0.7"
dirs = "5"
tower-http = { version = "0.5", features = ["cors"] }
```

### HttpPresetBank (WASM)

```cpp
// hal-sdl/src/oc/hal/sdl/HttpPresetBank.hpp

namespace oc::hal::sdl {

/**
 * @brief HTTP-based preset bank for WASM
 *
 * Communicates with oc-bridge via REST API.
 * Uses emscripten_fetch for async HTTP requests.
 */
class HttpPresetBank : public IPresetBank {
public:
    explicit HttpPresetBank(const std::string& baseUrl)
        : baseUrl_(baseUrl) {}

    // Sync operations (block on fetch)
    size_t count() const override;
    bool exists(uint8_t slot) const override;
    bool load(uint8_t slot, PresetData& out) override;
    bool save(uint8_t slot, const PresetData& data) override;
    // ...

private:
    std::string baseUrl_;  // e.g., "http://localhost:8080/storage/core/presets"

    // Blocking fetch helper
    bool fetchSync(const char* method, const char* url,
                   const uint8_t* body, size_t bodyLen,
                   std::vector<uint8_t>& response);
};

}  // namespace oc::hal::sdl
```

---

## 4. Sync Teensy ↔ Desktop

### Protocole (via Serial/USB)

```cpp
enum class PresetSyncMessage : uint8_t {
    // Desktop → Teensy
    LIST_REQUEST   = 0xE0,
    GET_REQUEST    = 0xE1,  // + slot
    PUT_REQUEST    = 0xE2,  // + slot + data
    DELETE_REQUEST = 0xE3,  // + slot

    // Teensy → Desktop
    LIST_RESPONSE  = 0xF0,  // + JSON
    GET_RESPONSE   = 0xF1,  // + binary preset
    ACK            = 0xF2,
    ERROR          = 0xF3,
};
```

### Flow

```
Desktop                          Teensy
   │                                │
   │──── LIST_REQUEST ─────────────►│
   │◄─── LIST_RESPONSE (JSON) ──────│
   │                                │
   │──── GET_REQUEST (slot=1) ─────►│
   │◄─── GET_RESPONSE (binary) ─────│
   │                                │
   │──── PUT_REQUEST (slot=2) ─────►│
   │◄─── ACK ───────────────────────│
```

---

## 5. Noms personnalisés

Extension `PresetInfo` :

```cpp
struct PresetInfo {
    uint8_t slot;
    uint8_t pageCount;
    char name[32];        // V2: User-defined name
    uint32_t modified;
};
```

Stocké dans le header du fichier preset (voir format fichier section 1).

---

## 6. GUI Manager

Interface web servie par oc-bridge pour :
- Lister les presets
- Renommer
- Dupliquer
- Supprimer
- Exporter/importer

**Stack suggéré** : HTML/CSS/JS statique servi par axum, appels REST.

---

## Chronologie suggérée

```
V1 stable
    │
    ├──► Multi-presets (FilePresetBank) ──► Noms personnalisés
    │
    ├──► LittleFS Teensy (après test hardware)
    │
    └──► Bridge HTTP ──► HttpPresetBank ──► Sync Teensy↔Desktop
                    │
                    └──► GUI Manager
```

---

## Règles de rétrocompatibilité

1. **Interfaces V1 stables** : `IStorageBackend`, `Settings<T>`, `PresetData`
2. **Méthodes additives** : Nouvelles méthodes avec défaut ou nullable
3. **Champs à la fin** : Nouveaux champs de struct ajoutés à la fin
4. **Magic numbers distincts** : V1 `OCST`, V2 presets `MSP2`
5. **Migration automatique** : V2 importe transparemment données V1
