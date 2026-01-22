# Draft: Generic Preset System Architecture

**Status**: Draft - À retravailler
**Created**: 2026-01-20
**Context**: Discussion sur l'évolution du système de presets

---

## Objectifs

- Données **hétérogènes** (MacroPage, Track, FX, Set, etc.)
- **Constructible** facilement (définir un type = struct + traits)
- **Appelable** facilement (save/load en une ligne)
- **Sérialisable** automatiquement
- **Lecture/écriture optimale**
- **Évolution** des structures supportée (migration legacy)

---

## Types de presets envisagés (futur)

| Catégorie | Type | Contenu | Taille estimée |
|-----------|------|---------|----------------|
| **Macro** | MacroPage | 8 macros | ~64B |
| | MacroSet | N pages | ~64-512B |
| **Sequencer** | Step | 1 step config | ~16-32B |
| | FX | fx globaux track | ~64B |
| | Track | sequence + fx | ~1-4KB |
| | Set | tracks complètes | ~10-50KB |

---

## Architecture proposée : Traits + Templates

### 1. Définir un type = struct POD + traits

```cpp
// La struct POD (données uniquement)
struct MacroPagePreset {
    std::array<float, 8> values;
    uint8_t channel;
    uint8_t ccStart;
};

// Les traits (metadata)
template<> struct PresetTraits<MacroPagePreset> {
    static constexpr uint8_t TYPE_ID = 1;
    static constexpr uint8_t VERSION = 1;
    static constexpr char NAME[] = "MacroPage";
};
```

### 2. Utilisation = une ligne

```cpp
PresetStore store(backend);

// Save/Load storage
MacroPagePreset preset{...};
store.save("my-preset", preset);
auto loaded = store.load<MacroPagePreset>("my-preset");

// Export/Import fichier (pour bridge desktop)
store.exportFile("/path/preset.msp", preset);
auto imported = store.importFile<MacroPagePreset>("/path/preset.msp");
```

### 3. Ajouter un nouveau type = 3 lignes

```cpp
struct TrackPreset {
    std::array<StepData, 64> steps;
    FXData fx;
};

template<> struct PresetTraits<TrackPreset> {
    static constexpr uint8_t TYPE_ID = 10;
    static constexpr uint8_t VERSION = 1;
};

// C'est tout - save/load/export marchent automatiquement
```

---

## Format binaire (storage interne)

```
┌────────────────────────────────────────┐
│ Header (16 bytes)                      │
├────────┬────────┬─────────┬───────────┤
│ magic  │ type   │ version │ size      │
│ 4B     │ 1B     │ 1B      │ 2B        │
├────────┴────────┴─────────┴───────────┤
│ checksum (4B) │ reserved (4B)         │
├───────────────────────────────────────┤
│ Payload (sizeof(T) bytes)             │
│ [memcpy direct de la struct POD]      │
└───────────────────────────────────────┘
```

---

## Gestion de l'évolution des structures

### Stratégie hybride

| Contexte | Format | Raison |
|----------|--------|--------|
| Storage interne (SD/EEPROM) | POD + version | Rapide, compact |
| Fichiers échange (bridge) | MessagePack ou JSON | Flexible, interop |

### Migration chainée (storage interne)

```cpp
// V1 (legacy)
struct MacroPagePresetV1 {
    std::array<float, 8> values;
    uint8_t cc_start;  // ancien nom
};

// V2 (actuel)
struct MacroPagePreset {
    std::array<float, 8> values;
    uint8_t ccStart;      // renommé
    uint8_t channel = 1;  // nouveau champ
};

template<> struct PresetTraits<MacroPagePreset> {
    static constexpr uint8_t TYPE_ID = 1;
    static constexpr uint8_t VERSION = 2;

    // Migration V1 → V2
    static MacroPagePreset migrate(uint8_t fromVersion, const uint8_t* data) {
        if (fromVersion == 1) {
            auto& v1 = *reinterpret_cast<const MacroPagePresetV1*>(data);
            return {
                .values = v1.values,
                .ccStart = v1.cc_start,
                .channel = 1  // default
            };
        }
        return {};
    }
};
```

### Format flexible pour fichiers (bridge)

```cpp
// Export → JSON/MessagePack
void exportFile(const char* path, const MacroPagePreset& p) {
    json j = {
        {"version", 2},
        {"type", "MacroPage"},
        {"values", p.values},
        {"ccStart", p.ccStart},
        {"channel", p.channel}
    };
}

// Import ← JSON/MessagePack avec fallbacks
MacroPagePreset importFile(const char* path) {
    auto j = json::parse(file);
    return {
        .values = j.value("values", defaultValues),
        .ccStart = j.value("ccStart", j.value("cc_start", 0)), // fallback ancien nom
        .channel = j.value("channel", 1)  // default si absent
    };
}
```

### Règles d'évolution

| Action | Support |
|--------|---------|
| Ajouter champ | ✅ Default dans import |
| Renommer champ | ✅ Fallback ancien nom |
| Supprimer champ | ✅ Ignorer à l'import |
| Changer type | ⚠️ Migration explicite |

---

## PresetStore API (ébauche)

```cpp
class PresetStore {
public:
    explicit PresetStore(IStorageBackend& backend);

    // ═══════════════════════════════════════════════════════════════
    // Storage interne (POD binaire)
    // ═══════════════════════════════════════════════════════════════

    template<typename T>
    bool save(const char* name, const T& preset);

    template<typename T>
    std::optional<T> load(const char* name);  // migrate si vieille version

    template<typename T>
    bool remove(const char* name);

    // List presets of type T
    template<typename T>
    std::vector<std::string> list();

    // ═══════════════════════════════════════════════════════════════
    // Fichiers (format flexible pour bridge)
    // ═══════════════════════════════════════════════════════════════

    template<typename T>
    bool exportFile(const char* path, const T& preset);

    template<typename T>
    std::optional<T> importFile(const char* path);

private:
    IStorageBackend& backend_;
};
```

---

## Questions ouvertes

1. **Nommage des presets** - String names ou IDs numériques ?
2. **Index/catalogue** - Comment lister les presets disponibles ?
3. **Taille variable** - Certains presets (Set) peuvent être gros, gérer comment ?
4. **Compression** - Utile pour les gros presets ?
5. **JSON vs MessagePack** - Lequel pour les fichiers bridge ?

---

## Prochaines étapes

1. Implémenter V1 simple (MacroSet uniquement) avec le système actuel
2. Valider le workflow save/load/export sur les 3 plateformes
3. Itérer vers cette architecture générique quand besoin réel
