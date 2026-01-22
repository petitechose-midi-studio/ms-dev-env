# Audit Architectural - Open Control Framework v1

> Analyse exhaustive de la codebase `open-control/framework`
> Date: 2026-01-21
> Scope: 83 fichiers source (70 .hpp, 13 .cpp) dans `src/oc/`

---

## Score Global: 4.3/5 ⭐⭐⭐⭐

| Critère | Score | Commentaire |
|---------|-------|-------------|
| Cohérence Absolue | 4/5 | Quelques violations mineures identifiées |
| Patterns Reproductibles | 5/5 | Règles claires et systématiquement appliquées |
| Extensibilité Sereine | 4/5 | Bon graphe de dépendances, quelques frictions |

---

## 1. Structure des Modules

```
oc/
├── api/          # APIs de haut niveau (ButtonAPI, EncoderAPI, MidiAPI)
├── app/          # Application principale (AppBuilder, OpenControlApp)
├── codec/        # Encodage (COBS)
├── context/      # Gestion des contextes (ContextManager, APIs, ContextBase)
├── core/         # Logique métier
│   ├── event/    # EventBus, Events, EventTypes
│   └── input/    # Bindings, Builders, GestureDetector, etc.
├── debug/        # Assertions d'invariants
├── impl/         # Implémentations null/mémoire (NullMidi, MemoryStorage)
├── interface/    # Interfaces HAL (IButton, IEncoder, IMidi, etc.)
├── log/          # Système de logging
├── state/        # État réactif (Signal, SignalWatcher, Settings)
├── time/         # Abstraction temps
├── types/        # Types fondamentaux (Ids, Callbacks, Result, Event)
└── util/         # Utilitaires
```

---

## 2. Hiérarchie de Dépendances (Validée)

```
Niveau 0: types/
    │     Ids.hpp, Callbacks.hpp, Event.hpp, Result.hpp
    │     AUCUNE dépendance interne ✓
    ▼
Niveau 1: interface/
    │     IButton, IEncoder, IMidi, IStorage, ITransport, IDisplay
    │     Dépend uniquement de types/ ✓
    ▼
Niveau 2: core/, state/
    │     EventBus, InputBinding, Signal, Settings
    │     Dépend de Niveau 0-1 ✓
    ▼
Niveau 3: api/, context/
    │     ButtonAPI, EncoderAPI, ContextManager, ContextBase
    │     Dépend de Niveau 0-2 ✓
    ▼
Niveau 4: app/
    │     AppBuilder, OpenControlApp
    │     Point de coordination ✓
    ▼
Niveau 5: impl/
          NullMidi, MemoryStorage, NullStorage
          Dépend de Niveau 1 ✓
```

**Résultat:** Aucun cycle de dépendances détecté. La règle unidirectionnelle est respectée.

---

## 3. Patterns Reproductibles (Excellents)

### 3.1 Fluent Builder Pattern

Appliqué systématiquement pour:
- `ButtonBuilder` (core/input/ButtonBuilder.hpp:31)
- `EncoderBuilder` (core/input/EncoderBuilder.hpp)
- `ComboBuilder` (core/input/ComboBuilder.hpp)
- `AppBuilder` (app/AppBuilder.hpp)

```cpp
class [[nodiscard]] ButtonBuilder {
    ButtonBuilder& press();
    ButtonBuilder& scope(ScopeID s);
    BindingHandle then(ActionCallback cb);  // Terminal obligatoire
};
```

### 3.2 Proxy Pattern

Appliqué pour:
- `ButtonProxy` (api/ButtonProxy.hpp)
- `EncoderProxy` (api/EncoderProxy.hpp)

### 3.3 Result<T> Pattern

Utilisé systématiquement pour les opérations faillibles:
- `IButton::init()` → `Result<void>`
- `IStorage::begin()` → `bool` (exception historique)
- `Settings::load()` → `Result<void>`

### 3.4 Signal/Subscription RAII

Pattern cohérent dans tout `state/`:
- `Signal<T>` → `Subscription` (auto-unsubscribe)
- `SignalVector<T>` → `Subscription`
- `SignalString` → `Subscription`
- `SignalWatcher` → gestion de groupe

### 3.5 Test de Placement (Validé)

| Si je crée... | Emplacement | Règle |
|---------------|-------------|-------|
| Interface HAL | `interface/I<Name>.hpp` | Préfixe I, dépend de types/ |
| API contexte | `api/<Name>API.hpp` | Dépend de core/input/ |
| Builder fluent | `core/input/<Name>Builder.hpp` | [[nodiscard]], terminal then() |
| Signal réactif | `state/Signal<T>.hpp` | Template header-only |
| Impl null/test | `impl/Null<Name>.hpp` | Dépend de interface/ |

---

## 4. Violations Identifiées

### 4.1 ⚠️ Deux Systèmes de Warning

| Fichier | Mécanisme | Usage |
|---------|-----------|-------|
| `core/Warning.hpp:61` | `oc::core::warn(const char*)` | ContextManager, InputBinding |
| `log/Log.hpp:211` | `OC_LOG_WARN(...)` | BindingRegistry |

**Problème:** Duplication fonctionnelle, incohérence dans le choix.

**Recommandation:** Unifier sur `OC_LOG_WARN` et supprimer `Warning.hpp`.

### 4.2 ⚠️ Placement de Binding.hpp

**Source:** `core/Binding.hpp`

Définit `ButtonBinding`, `EncoderBinding` avec dépendances:
- `types/Ids.hpp`
- `types/Callbacks.hpp`

**Problème:** Placé dans `core/` mais spécifique à `core/input/`.

**Recommandation:** Déplacer vers `core/input/Binding.hpp`.

### 4.3 ⚠️ Forward Declaration dans IContext

**Source:** `interface/IContext.hpp:12`

```cpp
namespace oc::context { struct APIs; }
```

**Problème:** Une interface (`interface/`) connaît l'existence d'un type dans `context/`.

**Recommandation:** Acceptable car forward declaration seulement, mais signale une tension architecturale. Alternative: extraire `IAPIsReceiver` dans `interface/`.

### 4.4 ℹ️ Singleton NotificationQueue

**Source:** `state/NotificationQueue.hpp`

```cpp
static NotificationQueue& instance() {
    static NotificationQueue instance;
    return instance;
}
```

**Impact:** Difficile à tester en parallèle, état global.

**Recommandation:** Faible priorité. Acceptable pour embedded, mais documenter la limitation.

---

## 5. Architecture des Encodeurs (Clarifiée)

Suite à l'analyse des HALs, l'architecture à 3 niveaux est **correcte et intentionnelle**:

```
┌─────────────────────────────────────────────────────────────┐
│                      Application                             │
│                           │                                  │
│                           ▼                                  │
│                      IEncoder                                │
│                    (interface/)                              │
└─────────────────────────────────────────────────────────────┘
                            │
        ┌───────────────────┴───────────────────┐
        │                                       │
        ▼                                       ▼
┌───────────────────┐                 ┌───────────────────┐
│  hal-teensy       │                 │  hal-sdl          │
│  EncoderController│                 │  SdlEncoderController │
├───────────────────┤                 ├───────────────────┤
│  IEncoderHardware │                 │  (pas de hardware │
│  (ISR-driven)     │                 │   physique)       │
│         │         │                 │                   │
│         ▼         │                 │                   │
│  EncoderLogic     │◄── partagé ───►│  EncoderLogic     │
│  (core/input/)    │                 │  (core/input/)    │
└───────────────────┘                 └───────────────────┘
```

| Interface | Rôle | Utilisé par |
|-----------|------|-------------|
| `IEncoderHardware` | Bas niveau, ISR-safe | hal-teensy uniquement |
| `EncoderLogic` | Logique partagée (modes, bounds) | Tous les HALs |
| `IEncoder` | Haut niveau, application | Tous les HALs |

**Verdict:** `IEncoderHardware` est **bien placé** dans `interface/`. C'est une interface optionnelle pour HALs avec hardware physique.

---

## 6. Métriques

### 6.1 Dépendances par Module

| Module | Includes internes | Évaluation |
|--------|-------------------|------------|
| `types/` | 0-1 | ✅ Parfait (Niveau 0) |
| `interface/` | 1-3 | ✅ Excellent (Niveau 1) |
| `core/event/` | 2-3 | ✅ Excellent |
| `state/` | 1-3 | ✅ Excellent |
| `core/input/` | 6-10 | ⚠️ Complexe mais justifié |
| `api/` | 8-10 | ⚠️ Élevé mais acceptable |
| `context/` | 6-8 | ✅ Correct |
| `app/` | 16 | ✅ Point de coordination |

### 6.2 Couverture de Tests

| Module | Tests | Couverture |
|--------|-------|------------|
| `state/Signal` | 25 tests | ✅ Excellente |
| `state/SignalVector` | Oui | ✅ Bonne |
| `state/Settings` | Oui | ✅ Bonne |
| `core/event/EventBus` | Oui | ✅ Bonne |
| `context/ContextManager` | Oui | ✅ Bonne |
| `core/input/InputBinding` | Oui | ⚠️ Partielle |

---

## 7. Recommandations Priorisées

### Priorité Haute (Impact fort, effort faible)

| Action | Fichiers concernés |
|--------|-------------------|
| Supprimer `Warning.hpp`, migrer vers `OC_LOG_WARN` | `core/Warning.hpp`, `ContextManager.cpp`, `InputBinding.cpp` |
| Déplacer `Binding.hpp` | `core/Binding.hpp` → `core/input/Binding.hpp` |

### Priorité Moyenne (Impact moyen, effort moyen)

| Action | Fichiers concernés |
|--------|-------------------|
| Documenter architecture encodeurs | `interface/IEncoderHardware.hpp`, README |
| Uniformiser `init()` vs `begin()` | `IStorage::begin()` → `init()` |

### Priorité Basse (Impact moyen, effort élevé)

| Action | Fichiers concernés |
|--------|-------------------|
| Extraire `IAPIsReceiver` | `interface/IContext.hpp` |
| Injecter `NotificationQueue` | `Signal.hpp`, `OpenControlApp.hpp` |

---

## 8. Points Forts

1. **Architecture en couches claire** - Les niveaux 0-4 sont strictement respectés
2. **Fluent API cohérente** - Builders uniformes avec pattern [[nodiscard]]
3. **Configuration flexible** - Compile-time via macros, run-time via injection
4. **Tests solides** - Bonne couverture des composants critiques
5. **Documentation Doxygen** - Présente et cohérente

---

## 9. Questions Ouvertes (À Explorer)

- [ ] Couverture de tests pour `core/input/InputBinding` (complexité élevée)
- [ ] Pattern d'erreur unifié: `Result<T>` partout vs `bool` pour certains HAL
- [ ] Documentation des HALs (hal-teensy, hal-sdl, hal-net)

---

*Prochaine étape: Affiner l'analyse sur les points identifiés*
