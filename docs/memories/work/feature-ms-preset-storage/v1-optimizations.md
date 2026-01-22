# V1 Optimizations: Zero-Boilerplate Persistence

**Date**: 2026-01-19
**Status**: ✅ Validé - LittleFS persistence confirmée

---

## Validation empirique LittleFS (2026-01-19)

Test sur Teensy 4.1 avec `midi-studio/tests/littlefs-persistence/` :

```
╔════════════════════════════════════════════════╗
║   SUCCESS: LittleFS PERSISTS across uploads!   ║
╚════════════════════════════════════════════════╝
```

**Conditions** :
- Bootloader >= 1.07 (auto-installé avec Teensyduino >= 1.56)
- Code < 512KB (test: ~60KB, bien sous la limite)
- Flash persistant: 7424KB disponibles

**Décision architecture** :
| Storage | Usage |
|---------|-------|
| **EEPROM** | Settings globaux uniquement (~64 bytes max) |
| **LittleFS** | Presets, séquences, config notes, note fx, etc. |

---

## Principe directeur

> **Le code applicatif doit être déclaratif et dépourvu de toute logique de persistence.**
> Le framework endosse 100% de la responsabilité d'implémentation.

### Objectif code applicatif

```cpp
// IDÉAL: Le code app ne fait que déclarer ses données
struct MyAppState {
    Signal<float> volume{0.5f};
    Signal<int> preset{0};
    std::array<Signal<float>, 8> macros;
};

// Le framework fait le reste automatiquement
Persistent<MyAppState> state(backend);
state.load();
// ... modifications via state->volume.set(0.8f) ...
// Auto-save géré par le framework
```

---

## État actuel (problèmes)

| Problème | Description |
|----------|-------------|
| **Persistence manuelle** | `CoreState` appelle explicitement `settings.saveValue()` |
| **Couplage fort** | Le code app connaît les offsets EEPROM |
| **Boilerplate** | Chaque Signal nécessite un `watchAt()` manuel |
| **Pas générique** | `AutoPersistIncremental` nécessite des callbacks custom |

---

## Architecture cible : Zero-Boilerplate

### Approche 1 : `Persistent<T>` wrapper automatique

Le framework fournit un wrapper qui gère tout automatiquement.

```cpp
// framework/src/oc/state/Persistent.hpp

namespace oc::state {

/**
 * @brief Zero-boilerplate persistence wrapper
 *
 * Wraps any POD struct and automatically:
 * - Tracks dirty state via snapshot comparison
 * - Saves with debounce
 * - Handles CRC32, versioning, migration
 *
 * App code only defines the data structure.
 */
template<typename T>
class Persistent {
    static_assert(std::is_trivially_copyable_v<T>);

public:
    Persistent(IStorageBackend& backend, uint32_t address = 0, uint16_t version = 1)
        : backend_(backend), address_(address), version_(version) {}

    /// Load from storage
    bool load() {
        // Read header + data, validate CRC
        // On failure: data_ = T{} (defaults)
        snapshot_ = data_;
        return true;
    }

    /// Check if modified since last save/load
    bool isDirty() const {
        return std::memcmp(&data_, &snapshot_, sizeof(T)) != 0;
    }

    /// Save if dirty (with debounce)
    void update(uint32_t now_ms) {
        if (!isDirty()) {
            dirty_since_ = 0;
            return;
        }
        if (dirty_since_ == 0) {
            dirty_since_ = now_ms;
        }
        if ((now_ms - dirty_since_) >= debounce_ms_) {
            save();
        }
    }

    /// Force save now
    void save() {
        // Write header + data + CRC
        snapshot_ = data_;
        dirty_since_ = 0;
    }

    /// Access data (const)
    const T& get() const { return data_; }

    /// Access data (mutable) - modifications auto-detected
    T& get() { return data_; }

    /// Arrow operator for convenience
    T* operator->() { return &data_; }
    const T* operator->() const { return &data_; }

private:
    IStorageBackend& backend_;
    uint32_t address_;
    uint16_t version_;
    uint32_t debounce_ms_ = 1000;
    uint32_t dirty_since_ = 0;

    T data_{};
    T snapshot_{};  // For dirty detection
};

} // namespace oc::state
```

### Usage code applicatif (ULTRA SIMPLE)

```cpp
// midi-studio/core/src/state/AppData.hpp

// 1. Définir les données (juste une struct POD)
struct AppData {
    uint8_t activePage = 0;
    uint8_t pageCount = 1;
    std::array<MacroPageData, 8> pages;
};

// C'est tout ! Pas de macros, pas d'interfaces.
```

```cpp
// midi-studio/core/main.cpp

// 2. Créer le wrapper persistant
oc::hal::FileStorageBackend storage("~/.config/app/data.bin");
oc::state::Persistent<AppData> appData(storage);
appData.load();

// 3. Utiliser comme une struct normale
appData->activePage = 2;
appData->pages[0].values[3] = 0.5f;

// 4. Dans la main loop
while (running) {
    // ... app logic ...
    appData.update(millis());  // Auto-save si dirty après debounce
}

appData.save();  // Final save
```

**Avantages** :
- Code app : ZERO connaissance de la persistence
- Dirty tracking automatique via snapshot comparison
- Compatible avec n'importe quel POD

**Inconvénients** :
- Double mémoire (data + snapshot)
- Pas de granularité fine (sauve tout le bloc)

---

### Approche 2 : `ReactiveStore<T>` avec Signals intégrés

Pour les données qui doivent être observables ET persistées.

```cpp
// framework/src/oc/state/ReactiveStore.hpp

namespace oc::state {

/**
 * @brief Combines reactive Signals with automatic persistence
 *
 * The store observes its own Signals and auto-saves on change.
 */
template<typename T>
class ReactiveStore {
public:
    ReactiveStore(IStorageBackend& backend) : persist_(backend) {}

    bool load() {
        if (!persist_.load()) return false;
        // Sync signals from loaded data
        syncSignalsFromData();
        return true;
    }

    // App accesses signals directly
    // Store watches them and updates persist_ automatically

protected:
    Persistent<T> persist_;

    // Override in derived class to sync signals ↔ data
    virtual void syncSignalsFromData() = 0;
    virtual void syncDataFromSignals() = 0;
};

} // namespace oc::state
```

**Usage** :

```cpp
// App-specific store
class MacroStore : public ReactiveStore<PresetData> {
public:
    // Signals exposés à l'app
    Signal<uint8_t> activePage{0};
    std::array<Signal<float>, 8> values;

    MacroStore(IStorageBackend& backend) : ReactiveStore(backend) {
        // Auto-sync signals → data
        activePage.subscribe([this](uint8_t v) {
            persist_->activePage = v;
        });
        // ... etc pour chaque signal
    }

protected:
    void syncSignalsFromData() override {
        activePage.set(persist_->activePage);
        // ...
    }
};
```

**Problème** : On retombe dans du boilerplate pour connecter signals ↔ data.

---

### Approche 3 : Macro-génération (RECOMMANDÉ pour V1)

Une seule macro génère tout : struct + signals + persistence.

```cpp
// framework/src/oc/state/Store.hpp

// Macro qui génère une classe store complète
#define OC_STORE(Name, ...)                                              \
    struct Name##Data { __VA_ARGS__ };                                   \
    class Name : public oc::state::Persistent<Name##Data> {              \
    public:                                                              \
        using oc::state::Persistent<Name##Data>::Persistent;             \
    }

// Alternative plus explicite avec fields nommés
#define OC_FIELD(type, name, default) type name = default;
```

**Usage** :

```cpp
// Déclaration ultra-compacte
OC_STORE(PresetStore,
    uint8_t activePage = 0;
    uint8_t pageCount = 1;
    std::array<MacroPageData, 8> pages;
);

// Utilisation
PresetStore presets(backend);
presets.load();
presets->activePage = 2;
presets.update(millis());
```

**Avantage** : Une seule déclaration, tout le reste généré.

---

## Recommandation finale pour V1

### Approche hybride simple

```cpp
// 1. Le framework fournit Persistent<T> (snapshot-based)
// 2. L'app définit juste ses structs POD
// 3. Pas de macros complexes, pas de reflection

// === Framework ===
template<typename T>
class Persistent { /* voir ci-dessus */ };

// === App ===
struct PresetData {
    uint8_t activePage = 0;
    uint8_t pageCount = 1;
    std::array<MacroPageData, 8> pages;
};

Persistent<PresetData> presets(backend);
```

### Ce que V2 ajoutera

```cpp
// V2: Extension pour JSON
template<typename T>
class Persistent {
    // ... V1 API ...

    // V2: Export/Import JSON (nécessite trait Serializable<T>)
    std::string toJson() const;
    bool fromJson(const std::string& json);
};

// V2: Macro pour déclarer Serializable automatiquement
OC_SERIALIZABLE(PresetData, activePage, pageCount, pages);
```

---

## Impact sur V1 tech-spec

Modifier `PresetManager` pour utiliser `Persistent<PresetData>` :

```cpp
class PresetManager {
public:
    PresetManager(IStorageBackend& backend)
        : data_(backend, 0, 1) {}

    bool init() {
        if (!data_.load()) {
            // Migration ou défaut
        }
        return true;
    }

    void update(uint32_t now_ms) {
        data_.update(now_ms);
    }

    // Accès direct aux données
    PresetData& data() { return data_.get(); }
    const PresetData& data() const { return data_.get(); }

private:
    Persistent<PresetData> data_;
};
```

**Code app** :

```cpp
// main.cpp
PresetManager presets(storage);
presets.init();

// Accès simple
presets.data().activePage = 2;
presets.data().pages[0].values[3] = 0.75f;

// Main loop
while (running) {
    presets.update(millis());
}
```

---

## Résumé

| Aspect | V1 | V2 |
|--------|----|----|
| **Persistence** | `Persistent<T>` snapshot-based | Idem |
| **Dirty tracking** | Auto via memcmp | Idem |
| **Granularité** | Bloc entier | Potentiellement par champ |
| **JSON** | Non | `Serializable<T>` trait + macros |
| **Code app** | Définit struct POD, utilise `data()` | Idem + JSON optionnel |

**Effort V1** : +4h (créer `Persistent<T>`, adapter `PresetManager`)
**Bénéfice** : Code app sans boilerplate, framework gère tout
