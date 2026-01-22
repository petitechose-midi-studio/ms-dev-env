# Audit Architectural - Open Control Framework v2

> Analyse exhaustive de la codebase `open-control/framework`
> Date: 2026-01-21
> Scope: 83 fichiers source (70 .hpp, 13 .cpp) dans `src/oc/`

---

## Score Global: 4.3/5 ⭐⭐⭐⭐

| Critère | Score | Commentaire |
|---------|-------|-------------|
| Cohérence Absolue | 4/5 | Violations mineures identifiées (Warning/Log, Result/bool) |
| Patterns Reproductibles | 5/5 | Règles claires et systématiquement appliquées |
| Extensibilité Sereine | 4/5 | Bon graphe de dépendances, architecture 3 niveaux validée |

---

## 1. Structure Complète des Modules

```
oc/
├── api/          # APIs de haut niveau (façades pour contextes)
│   ├── ButtonAPI.hpp/cpp
│   ├── EncoderAPI.hpp/cpp
│   ├── MidiAPI.hpp/cpp
│   ├── ButtonProxy.hpp
│   └── EncoderProxy.hpp
├── app/          # Application principale (assemblage)
│   ├── AppBuilder.hpp
│   └── OpenControlApp.hpp/cpp
├── codec/        # Encodage protocole
│   └── CobsCodec.hpp
├── context/      # Gestion des contextes
│   ├── ContextManager.hpp/cpp
│   ├── ContextBase.hpp
│   ├── APIs.hpp
│   └── Requirements.hpp
├── core/         # Logique métier
│   ├── Binding.hpp
│   ├── Warning.hpp          ⚠️ À supprimer
│   ├── event/
│   │   ├── EventBus.hpp/cpp
│   │   ├── Events.hpp
│   │   └── EventTypes.hpp
│   └── input/
│       ├── InputBinding.hpp/cpp
│       ├── InputConfig.hpp
│       ├── ButtonBuilder.hpp/cpp
│       ├── EncoderBuilder.hpp/cpp
│       ├── ComboBuilder.hpp/cpp
│       ├── BindingRegistry.hpp
│       ├── BindingHandle.hpp
│       ├── GestureDetector.hpp/cpp
│       ├── EncoderLogic.hpp/cpp
│       ├── AuthorityResolver.hpp
│       ├── LatchManager.hpp
│       ├── OwnershipTracker.hpp
│       └── Traits.hpp
├── debug/        # Assertions d'invariants
│   └── InvariantAssert.hpp
├── impl/         # Implémentations null/mock
│   ├── NullMidi.hpp
│   ├── NullStorage.hpp
│   └── MemoryStorage.hpp
├── interface/    # Interfaces HAL (Niveau 1)
│   ├── IButton.hpp
│   ├── IEncoder.hpp
│   ├── IEncoderHardware.hpp
│   ├── IMidi.hpp
│   ├── IStorage.hpp          ⚠️ begin() → bool au lieu de Result<void>
│   ├── ITransport.hpp
│   ├── IDisplay.hpp
│   ├── IMultiplexer.hpp
│   ├── IContext.hpp          ⚠️ initialize() → bool au lieu de Result<void>
│   ├── IContextSwitcher.hpp
│   └── IEventBus.hpp
├── log/          # Système de logging
│   └── Log.hpp
├── state/        # État réactif (signals)
│   ├── Signal.hpp
│   ├── SignalString.hpp
│   ├── SignalVector.hpp
│   ├── SignalWatcher.hpp
│   ├── DerivedSignal.hpp
│   ├── Bind.hpp
│   ├── Settings.hpp
│   ├── AutoPersist.hpp
│   ├── AutoPersistIncremental.hpp
│   ├── ExclusiveVisibilityStack.hpp
│   └── NotificationQueue.hpp/cpp
├── time/         # Abstraction temps
│   └── Time.hpp/cpp
├── types/        # Types fondamentaux (Niveau 0)
│   ├── Ids.hpp
│   ├── Callbacks.hpp
│   ├── Result.hpp
│   └── Event.hpp
└── util/         # Utilitaires
    └── Index.hpp
```

---

## 2. Violations Identifiées

### 2.1 🔴 Deux Systèmes de Warning (Haute Priorité)

**Cartographie complète des usages:**

| Mécanisme | Fichier | Usages |
|-----------|---------|--------|
| `core::warn()` | `core/Warning.hpp:61` | 10 appels |
| `OC_LOG_WARN()` | `log/Log.hpp:211` | 5 appels |

**Usages de `core::warn()`:**
```
api/MidiAPI.cpp:12     - Invalid channel
api/MidiAPI.cpp:21     - Invalid value
api/MidiAPI.cpp:30     - Invalid pitch bend
api/MidiAPI.cpp:67     - Invalid SysEx data
context/ContextManager.hpp:141 - ButtonAPI required but none
context/ContextManager.hpp:145 - EncoderAPI required but none
context/ContextManager.hpp:149 - MidiAPI required but none
context/ContextManager.hpp:153 - ITransport required but none
context/ContextManager.cpp:68  - Default context failed to create
context/ContextManager.cpp:80  - Default context failed to init
core/input/InputBinding.cpp:23 - No TimeProvider
```

**Usages de `OC_LOG_WARN()`:**
```
app/OpenControlApp.cpp:124     - Subscriptions overflow
app/OpenControlApp.cpp:133     - Notifications overflow
state/NotificationQueue.cpp:43 - Queue overflow
core/event/EventBus.cpp:28     - Max subscribers reached
core/input/BindingRegistry.hpp:49 - Max bindings reached
```

**Recommandation:** Migrer tous les `core::warn()` vers `OC_LOG_WARN()` et supprimer `Warning.hpp`.

---

### 2.2 🔴 Incohérence Result<T> vs bool (Haute Priorité)

| Interface | Méthode | Retour | Attendu |
|-----------|---------|--------|---------|
| `IButton` | `init()` | `Result<void>` | ✅ |
| `IEncoder` | `init()` | `Result<void>` | ✅ |
| `IEncoderHardware` | `init()` | `Result<void>` | ✅ |
| `IMidi` | `init()` | `Result<void>` | ✅ |
| `IDisplay` | `init()` | `Result<void>` | ✅ |
| `ITransport` | `init()` | `Result<void>` | ✅ |
| `IMultiplexer` | `init()` | `Result<void>` | ✅ |
| **`IStorage`** | **`begin()`** | **`bool`** | ⚠️ `Result<void>` |
| **`IContext`** | **`initialize()`** | **`bool`** | ⚠️ `Result<void>` |

**Problèmes:**
1. `IStorage::begin()` retourne `bool` - perte d'information d'erreur
2. `IContext::initialize()` retourne `bool` - incohérent avec les autres interfaces
3. Nommage: `begin()` vs `init()` - ambiguïté sémantique

**Recommandation:**
```cpp
// IStorage.hpp - Avant
virtual bool begin() = 0;

// IStorage.hpp - Après
virtual oc::Result<void> init() = 0;

// IContext.hpp - Avant
virtual bool initialize() = 0;

// IContext.hpp - Après
virtual oc::Result<void> init() = 0;
```

---

### 2.3 🟡 Placement de Binding.hpp (Moyenne Priorité)

**Source:** `core/Binding.hpp`

**Problème:** Définit `ButtonBinding`, `EncoderBinding` mais placé dans `core/` au lieu de `core/input/`.

**Dépendances:**
- `types/Ids.hpp` ✅
- `types/Callbacks.hpp` ✅

**Utilisé par:**
- `core/input/BindingRegistry.hpp`
- `core/input/InputBinding.hpp`
- `core/input/ButtonBuilder.hpp`
- `core/input/EncoderBuilder.hpp`

**Recommandation:** Déplacer vers `core/input/Binding.hpp`.

---

### 2.4 🟡 Forward Declaration dans IContext (Moyenne Priorité)

**Source:** `interface/IContext.hpp:12`

```cpp
namespace oc::context { struct APIs; }
```

**Problème:** Couplage conceptuel interface → implémentation.

**Impact:** Acceptable car forward declaration seulement, mais crée une dépendance implicite.

**Alternatives:**
1. Accepter (statu quo) - justifier dans les commentaires
2. Extraire `IAPIsReceiver` dans `interface/` - plus pur mais plus de fichiers

---

### 2.5 🟢 Singleton NotificationQueue (Basse Priorité)

**Source:** `state/NotificationQueue.hpp:82`

```cpp
static NotificationQueue& instance();
```

**Impact:**
- État global → difficile à tester en parallèle
- Acceptable pour embedded single-threaded

**Documentation existante:** Le commentaire documente "NOT thread-safe".

**Recommandation:** Documenter cette limitation dans le README.

---

## 3. Architecture des Encodeurs (Validée)

L'architecture à 3 niveaux est correcte et intentionnelle:

```
┌─────────────────────────────────────────────────────────────┐
│                         Application                          │
│                              │                               │
│                              ▼                               │
│                         IEncoder                             │
│                       (interface/)                           │
└─────────────────────────────────────────────────────────────┘
                               │
           ┌───────────────────┴───────────────────┐
           │                                       │
           ▼                                       ▼
┌─────────────────────┐                 ┌─────────────────────┐
│  hal-teensy         │                 │  hal-sdl            │
│  EncoderController  │                 │  SdlEncoderController│
├─────────────────────┤                 ├─────────────────────┤
│  IEncoderHardware   │                 │  (pas de hardware   │
│  (ISR-driven)       │                 │   physique)         │
│         │           │                 │                     │
│         ▼           │                 │                     │
│  EncoderLogic       │◄── partagé ───►│  EncoderLogic       │
│  (core/input/)      │                 │  (core/input/)      │
└─────────────────────┘                 └─────────────────────┘
```

**Verdict:** `IEncoderHardware` est bien placé dans `interface/` comme interface optionnelle pour HALs avec hardware physique.

---

## 4. Patterns Validés (Excellents)

### 4.1 Fluent Builder Pattern

```cpp
// Toujours [[nodiscard]], terminé par then()
class [[nodiscard]] ButtonBuilder {
    ButtonBuilder& press();
    ButtonBuilder& longPress(uint32_t ms);
    ButtonBuilder& scope(ScopeID s);
    BindingHandle then(ActionCallback cb);  // Terminal
};
```

Appliqué à: `ButtonBuilder`, `EncoderBuilder`, `ComboBuilder`, `AppBuilder`

### 4.2 RAII Subscription Pattern

```cpp
// Tous les signals utilisent ce pattern
class Subscription {
    ~Subscription() { reset(); }  // Auto-unsubscribe
};
```

Appliqué à: `Signal<T>`, `SignalString`, `SignalVector`, `SignalWatcher`, `EventBus`

### 4.3 Deferred Notification Pattern

```cpp
// NotificationQueue pour coalescing automatique
Signal::set() → enqueue notification
OpenControlApp::update() → flush() → callbacks exécutés
```

**Avantages:**
- Coalescing automatique (même signal set N fois → 1 callback)
- ISR-safe (pas de callback en contexte ISR)
- BatchGuard RAII pour updates atomiques

### 4.4 Result<T> Error Handling

```cpp
Result<void>::ok();
Result<void>::err({ErrorCode::HARDWARE_INIT_FAILED, "context"});
```

Utilisé systématiquement sauf pour `IStorage` et `IContext` (cf. violations).

---

## 5. Modules Secondaires (Validés)

### 5.1 codec/CobsCodec.hpp
- COBS streaming decoder
- Compatible avec oc-bridge (Rust)
- Header-only, zero-allocation après construction

### 5.2 debug/InvariantAssert.hpp
- Macros d'assertion pour invariants architecturaux
- `OC_ASSERT_SINGLE_SOURCE_OF_TRUTH`, `OC_ASSERT_INPUT_AUTHORITY`, etc.
- Compilé out en release (NDEBUG)

### 5.3 time/Time.hpp
- Abstraction plateforme-agnostic
- HAL injecte le provider via `setProvider()`
- Framework utilise `oc::time::millis()`

### 5.4 util/Index.hpp
- `wrapIndex()` pour navigation circulaire
- `shouldPrefetch()` pour chargement windowed

---

## 6. État Réactif (state/) - Analyse Complète

| Classe | Rôle | Allocation |
|--------|------|------------|
| `Signal<T>` | Valeur observable | Fixed (template) |
| `SignalString` | String observable 128 chars | Fixed buffer |
| `SignalLabel` | String observable 32 chars | Fixed buffer |
| `SignalVector<T,N>` | Collection observable | Fixed array |
| `DerivedSignal<In,Out>` | Signal calculé | Subscription interne |
| `Binder` | Fluent subscription builder | Reference to vector |
| `Settings<T>` | Persistence avec migration | Fixed |
| `AutoPersist<T>` | Debounced save | Subscriptions vector |
| `ExclusiveVisibilityStack` | UI overlays | Fixed array |

**Pattern commun:** Tous non-copyable, non-movable (subscribers hold pointers).

---

## 7. Métriques Finales

### 7.1 Lignes de Code par Module

| Module | .hpp | .cpp | Total |
|--------|------|------|-------|
| types/ | ~200 | 0 | ~200 |
| interface/ | ~400 | 0 | ~400 |
| state/ | ~1200 | ~100 | ~1300 |
| core/input/ | ~800 | ~500 | ~1300 |
| core/event/ | ~200 | ~100 | ~300 |
| context/ | ~400 | ~150 | ~550 |
| api/ | ~300 | ~100 | ~400 |
| app/ | ~300 | ~180 | ~480 |
| **Total** | **~4000** | **~1100** | **~5100** |

### 7.2 Tests Couverts

- `test_signal/` - Signal<T>, SignalVector, SignalString ✅
- `test_settings/` - Settings<T> ✅
- `test_event_bus/` - EventBus ✅
- `test_input_binding/` - InputBinding (partiel)
- `test_context_manager/` - ContextManager ✅

---

## 8. Recommandations Consolidées

### Priorité Haute

| # | Action | Impact |
|---|--------|--------|
| 1 | Supprimer `Warning.hpp`, migrer vers `OC_LOG_WARN` | Uniformisation logging |
| 2 | `IStorage::begin()` → `init()` retournant `Result<void>` | Cohérence API |
| 3 | `IContext::initialize()` → `init()` retournant `Result<void>` | Cohérence API |

### Priorité Moyenne

| # | Action | Impact |
|---|--------|--------|
| 4 | Déplacer `Binding.hpp` vers `core/input/` | Organisation logique |
| 5 | Documenter l'architecture encodeurs dans README | Clarté pour contributeurs |

### Priorité Basse

| # | Action | Impact |
|---|--------|--------|
| 6 | Documenter limitation singleton NotificationQueue | Testabilité |
| 7 | Ajouter tests InputBinding pour gestures complexes | Couverture |

---

## 9. Conclusion

La codebase `open-control/framework` est de **bonne qualité** avec une architecture cohérente et des patterns bien appliqués. Les violations identifiées sont mineures et facilement corrigibles.

**Points forts:**
- Hiérarchie de dépendances stricte (5 niveaux)
- Patterns reproductibles (Fluent Builder, RAII Subscription)
- État réactif sans allocation (embedded-friendly)
- Documentation Doxygen systématique

**Axes d'amélioration:**
- Unification Warning/Log
- Cohérence Result<T> dans toutes les interfaces
- Quelques réorganisations de fichiers mineures

---

*Prochaine étape: Analyse des HALs (hal-teensy, hal-sdl, hal-net)*
