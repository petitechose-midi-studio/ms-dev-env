# Audit Architectural Complet - Open Control Framework (v3)

> **Date:** 2026-01-20
> **Statut:** Analyse exhaustive - Vision d'ensemble
> **Fichiers analysés:** 75+ fichiers source

---

## Vue d'Ensemble des Modules

### Structure des Projets

```
open-control/
├── framework/           # Core framework (analyse principale)
├── hal-common/          # Types partagés pour HALs embarqués
├── hal-midi/            # HAL libremidi (desktop)
├── hal-net/             # HAL réseau (UDP, WebSocket)
├── hal-sdl/             # HAL SDL (desktop simulation)
├── hal-teensy/          # HAL Teensy 4.x
├── ui-lvgl/             # Bridge LVGL
└── ui-lvgl-components/  # Composants LVGL réutilisables
```

---

## Inventaire Complet des Fichiers du Framework

### oc/types/ (N'EXISTE PAS - À CRÉER)

| Fichier proposé | Contenu à migrer |
|-----------------|------------------|
| `Ids.hpp` | `ButtonID`, `EncoderID`, `BindingID`, `ScopeID` |
| `Callbacks.hpp` | `ButtonCallback`, `EncoderCallback`, `TimeProvider`, `IsActiveFn`, `ActionCallback` |
| `Result.hpp` | `Result<T>`, `ErrorCode`, `Error` |
| `Event.hpp` | `Event`, `EventType`, `EventCategoryType` (depuis core/event/) |

### oc/interface/ (13 fichiers)

| Fichier | Conformité | Issues |
|---------|------------|--------|
| `IButton.hpp` | ⚠️ | Dépend de `core/Result.hpp` |
| `IContext.hpp` | ❌ | **Anti-pattern 6.1** - Classe avec implémentation, pas interface |
| `IContextSwitcher.hpp` | ✅ | Interface pure avec templates inline |
| `IDisplay.hpp` | ⚠️ | Dépend de `core/Result.hpp` |
| `IEncoder.hpp` | ⚠️ | Dépend de `core/Result.hpp` |
| `IEncoderHardware.hpp` | ⚠️ | Dépend de `core/Result.hpp` |
| `IEventBus.hpp` | ❌ | Dépend de `core/event/Event.hpp` |
| `IGpio.hpp` | ✅ | Interface pure |
| `IMidi.hpp` | ⚠️ | Dépend de `core/Result.hpp` |
| `IMultiplexer.hpp` | ⚠️ | Dépend de `core/Result.hpp` |
| `IStorage.hpp` | ✅ | Interface pure - **MODÈLE À SUIVRE** |
| `ITransport.hpp` | ⚠️ | Dépend de `core/Result.hpp` |
| `Types.hpp` | ❌ | **Anti-pattern 6.3** - namespace `oc` dans fichier `interface/` |

**Bilan interfaces:** 3/13 conformes (23%)

### oc/core/ (17 fichiers)

| Fichier | Conformité | Notes |
|---------|------------|-------|
| `Result.hpp` | ⚠️ | **Devrait être dans `types/`** |
| `Warning.hpp` | ✅ | Header-only, bien isolé |
| **core/event/** | | |
| `Event.hpp` | ⚠️ | Devrait être niveau 0-1 |
| `EventBus.hpp` | ✅ | Implémente IEventBus correctement |
| `EventBus.cpp` | ✅ | |
| `Events.hpp` | ✅ | Events concrets, dépend de Types.hpp |
| `EventTypes.hpp` | ✅ | Constantes uniquement |
| **core/input/** | | |
| `AuthorityResolver.hpp` | ✅ | Bien conçu, header-only |
| `BindingHandle.hpp/cpp` | ✅ | Namespace `oc::core` (devrait être `oc::core::input`) |
| `ButtonBuilder.hpp/cpp` | ⚠️ | Code dupliqué avec EncoderBuilder |
| `ComboBuilder.hpp/cpp` | ⚠️ | Code dupliqué (trait SFINAE) |
| `EncoderBuilder.hpp/cpp` | ⚠️ | Code dupliqué avec ButtonBuilder |
| `EncoderLogic.hpp/cpp` | ✅ | Bien conçu, atomic pour ISR |
| `InputBinding.hpp/cpp` | ❌ | **God Object** - 790 lignes, 5+ responsabilités |
| `InputConfig.hpp` | ⚠️ | Namespace `oc::core` au lieu de `oc::core::input` |
| **core/struct/** | | |
| `Binding.hpp` | ⚠️ | Namespace `oc::core` au lieu de `oc::core::struct` |

### oc/api/ (8 fichiers)

| Fichier | Conformité | Notes |
|---------|------------|-------|
| `ButtonAPI.hpp/cpp` | ✅ | Façade bien conçue |
| `ButtonProxy.hpp` | ✅ | Proxy léger |
| `EncoderAPI.hpp/cpp` | ✅ | Façade bien conçue |
| `EncoderProxy.hpp` | ✅ | Proxy léger |
| `MidiAPI.hpp/cpp` | ✅ | Façade bien conçue |

**Bilan api/:** 100% conforme - **MODÈLE À SUIVRE**

### oc/context/ (4 fichiers)

| Fichier | Conformité | Notes |
|---------|------------|-------|
| `APIs.hpp` | ✅ | Container de services |
| `ContextManager.hpp/cpp` | ✅ | Bien structuré |
| `Requirements.hpp` | ✅ | SFINAE helper |

### oc/app/ (4 fichiers)

| Fichier | Conformité | Notes |
|---------|------------|-------|
| `AppBuilder.hpp/cpp` | ✅ | Builder pattern |
| `OpenControlApp.hpp/cpp` | ⚠️ | Ordre de destruction critique (documenté) |

### oc/state/ (12 fichiers)

| Fichier | Conformité | Notes |
|---------|------------|-------|
| `Signal.hpp` | ✅ | Excellente conception |
| `SignalString.hpp` | ✅ | Variante string |
| `SignalVector.hpp` | ✅ | Variante vector |
| `SignalWatcher.hpp` | ✅ | Coalescing pattern |
| `NotificationQueue.hpp/cpp` | ✅ | Deferred notifications |
| `Settings.hpp` | ✅ | Persistence avec CRC |
| `AutoPersist.hpp` | ✅ | Debounced saves |
| `AutoPersistIncremental.hpp` | ✅ | Incremental saves |
| `Bind.hpp` | ✅ | Fluent subscription builder |
| `DerivedSignal.hpp` | ✅ | Computed signals |
| `ExclusiveVisibilityStack.hpp` | ✅ | Overlay management |

**Bilan state/:** 100% conforme - **MODULE EXEMPLAIRE**

### oc/impl/ (3 fichiers)

| Fichier | Conformité | Notes |
|---------|------------|-------|
| `MemoryStorage.hpp` | ✅ | Implémente IStorage |
| `NullMidi.hpp` | ✅ | Null object pattern |
| `NullStorage.hpp` | ✅ | Null object pattern |

### Autres modules

| Module | Fichiers | Conformité |
|--------|----------|------------|
| `oc/codec/` | CobsCodec.hpp | ✅ |
| `oc/debug/` | InvariantAssert.hpp | ✅ |
| `oc/log/` | Log.hpp/cpp, ProtocolOutput.hpp | ✅ |
| `oc/time/` | Time.hpp/cpp | ⚠️ Duplique TimeProvider |
| `oc/util/` | Index.hpp | ✅ |
| `oc/Config.hpp` | | ⚠️ Namespace ≠ chemin |

---

## HALs - Conformité des Namespaces

| HAL | Namespace | Conformité |
|-----|-----------|------------|
| hal-sdl | `oc::hal::sdl` | ✅ |
| hal-teensy | `oc::hal::teensy` | ✅ |
| hal-common | `oc::hal::common::embedded` | ✅ |
| hal-midi | `oc::hal::midi` | ✅ |
| hal-net | `oc::hal::net` | ✅ |

**Tous les HALs respectent la convention namespace = chemin**

---

## Synthèse des Violations

### Par Catégorie

| Catégorie | Count | Sévérité |
|-----------|-------|----------|
| Interface avec implémentation | 1 | Critique |
| Dépendance interface → core | 8 | Critique |
| Namespace ≠ chemin | 6 | Modérée |
| Code dupliqué | 3 | Faible |
| God Object | 1 | À traiter séparément |

### Par Fichier (Actions Requises)

#### Priorité CRITIQUE

1. **`oc/interface/IContext.hpp`**
   - Action: Scinder en `IContext` (pure) + `ContextBase` (dans context/)
   - Impact: Migration code utilisateur

2. **`oc/interface/Types.hpp`**
   - Action: Déplacer vers `oc/types/Ids.hpp` avec namespace `oc`
   - Impact: ~20 fichiers à mettre à jour

3. **`oc/core/Result.hpp`**
   - Action: Déplacer vers `oc/types/Result.hpp`
   - Impact: 8 interfaces + 10+ HALs

4. **`oc/core/event/Event.hpp`**
   - Action: Déplacer vers `oc/types/Event.hpp` ou `oc/event/Event.hpp`
   - Impact: IEventBus, Events.hpp

#### Priorité HAUTE

5. **`oc/interface/IEventBus.hpp`**
   - Action: Utiliser `types/Event.hpp` après migration
   - Dépend de: #4

6. **8 interfaces avec `#include <oc/core/Result.hpp>`**
   - Action: Changer en `#include <oc/types/Result.hpp>`
   - Dépend de: #3

#### Priorité MODÉRÉE

7. **`oc/Config.hpp`**
   - Action: Changer namespace `oc::config` → `oc`
   - OU déplacer vers `oc/config/Config.hpp`

8. **`oc/core/input/InputConfig.hpp`**
   - Action: Changer namespace `oc::core` → `oc::core::input`

9. **`oc/core/struct/Binding.hpp`**
   - Action: Changer namespace `oc::core` → `oc::core::struct`

10. **`oc/time/Time.hpp`**
    - Action: Supprimer définition dupliquée de `TimeProvider`
    - Utiliser `oc/types/Callbacks.hpp`

#### Priorité FAIBLE (Refactoring)

11. **`ButtonBuilder`, `EncoderBuilder`, `ComboBuilder`**
    - Action: Extraire trait SFINAE commun
    - Impact: Qualité code, pas fonctionnel

12. **`InputBinding` (God Object)**
    - Action: Refactorer en classes spécialisées
    - Impact: Maintenabilité
    - **Décision:** Traiter APRÈS les corrections architecturales

---

## Décisions Confirmées

| # | Décision | Justification |
|---|----------|---------------|
| 1 | IContext → IContext (pure) + ContextBase + ContextAPI | Conformité Clean Architecture |
| 2 | Result<T> → `oc/types/` | Supprimer 8 inversions de dépendances |
| 3 | TimeProvider → `oc/types/Callbacks.hpp` (unique) | Éliminer duplication |
| 4 | Corriger TOUTES les violations | Pas d'exceptions documentées |
| 5 | InputBinding refactoring → Phase 2 | Après corrections architecturales |
| 6 | OpenControlApp ordre destruction → NE PAS modifier | Bénéfice nul en production |
| 7 | std::function → Pas de changement | OK pour cibles (Teensy 4.x, STM32, ESP32) |

---

## Modules Exemplaires (À Imiter)

1. **`oc/state/`** - Architecture réactive propre
2. **`oc/api/`** - Façades bien conçues
3. **`oc/interface/IStorage.hpp`** - Interface pure modèle
4. **HALs** - Namespaces corrects, dépendances appropriées

---

## Prochaine Étape

Produire un **plan de migration détaillé** avec:
1. Ordre des opérations (dépendances entre fichiers)
2. Scripts de migration ou commandes
3. Tests à exécuter après chaque étape
4. Points de validation

---

*Document généré lors de l'audit architectural complet - Itération 3*
