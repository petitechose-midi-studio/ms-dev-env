# Open Control - Analyse Architecturale Complète

> Analyse approfondie de l'écosystème open-control
> Date: 2026-01-20

---

## 1. Vue d'Ensemble des Repos

```
open-control/
├── framework/              # Core du système (59 fichiers .hpp)
├── hal-common/             # Types partagés embedded (4 fichiers)
├── hal-teensy/             # Implémentation Teensy (14 fichiers)
├── hal-sdl/                # Implémentation SDL (vide)
├── hal-midi/               # Implémentation MIDI (vide)
├── hal-net/                # Implémentation Network (vide)
├── ui-lvgl/                # Bridge LVGL (11 fichiers)
├── ui-lvgl-components/     # Widgets LVGL réutilisables (13 fichiers)
├── protocol-codegen/       # Générateur de protocole (Python)
├── bridge/                 # Bridge Rust
└── examples-*/             # Exemples d'utilisation
```

---

## 2. Graphe de Dépendances Actuel

```
                    ┌─────────────────────┐
                    │  ui-lvgl-components │
                    │  (widgets, themes)  │
                    └─────────┬───────────┘
                              │ dépend de IWidget, IComponent
                              ▼
                    ┌─────────────────────┐
                    │      ui-lvgl        │
                    │ (Bridge, IView...)  │
                    └─────────┬───────────┘
                              │ dépend de IDisplay, Result, Types
                              ▼
┌─────────────┐     ┌─────────────────────┐     ┌─────────────┐
│ hal-teensy  │────▶│     framework       │◀────│ hal-common  │
│ (drivers)   │     │ (core du système)   │     │ (ButtonDef) │
└─────────────┘     └─────────────────────┘     └─────────────┘
       │                      ▲
       │                      │
       └──────────────────────┘
              dépend de interface/, core/
```

---

## 3. Analyse du Framework (Module Central)

### 3.1 Structure Actuelle

```
framework/src/oc/
├── interface/          # 13 fichiers - "Interfaces" (mélangé)
│   ├── I*.hpp          # Interfaces HAL pures (IButton, IMidi...)
│   ├── IContext.hpp    # ⚠️ Classe de base, pas interface
│   ├── IEventBus.hpp   # ⚠️ Dépend de core/event/Event.hpp
│   └── Types.hpp       # ⚠️ namespace oc (pas oc::interface)
├── core/               # 15 fichiers - Logique métier
│   ├── Result.hpp      # ⚠️ Utilisé par interface/
│   ├── event/          # Event system
│   ├── input/          # Input bindings
│   └── struct/         # Structures communes
├── api/                # 5 fichiers - Façades utilisateur
├── app/                # 2 fichiers - Assemblage
├── impl/               # 3 fichiers - Mocks (NullMidi, NullStorage)
├── context/            # 3 fichiers - Gestion contextes
├── state/              # 10 fichiers - Reactive state (Signal)
├── log/                # 2 fichiers - Logging
├── time/               # 1 fichier - Time provider
├── codec/              # 1 fichier - COBS codec
├── debug/              # 1 fichier - Assertions
├── util/               # 1 fichier - Utilitaires
└── Config.hpp          # Configuration globale
```

### 3.2 Problèmes Identifiés

| # | Fichier | Problème | Principe Violé |
|---|---------|----------|----------------|
| 1 | `interface/Types.hpp` | Définit dans `namespace oc` mais fichier dans `interface/` | Namespace = Chemin |
| 2 | `interface/IEventBus.hpp` | Dépend de `core/event/Event.hpp` | Dependency Rule |
| 3 | `interface/IContext.hpp` | Classe avec implémentation, pas interface pure | ISP |
| 4 | `interface/IContext.hpp` | Dépend de `api/*` et `core/input/*` | Dependency Rule |
| 5 | `interface/I*.hpp` | Dépendent de `core/Result.hpp` | Dependency Rule |
| 6 | `core/Result.hpp` | Type fondamental dans module métier | Layering |

### 3.3 Analyse des Dépendances interface/ → core/

```cpp
// interface/IEventBus.hpp (PROBLÈME)
#include <oc/core/event/Event.hpp>  // Interface dépend de core!

// interface/IContext.hpp (PROBLÈME)
#include <oc/api/ButtonAPI.hpp>      // Interface dépend de api!
#include <oc/core/input/ButtonBuilder.hpp>  // Interface dépend de core!

// interface/IButton.hpp (PROBLÈME)
#include <oc/core/Result.hpp>  // Interface dépend de core!
```

**Impact:** Le module `interface/` ne peut pas être considéré comme la couche la plus basse car il a des dépendances ascendantes.

---

## 4. Analyse des HALs

### 4.1 hal-common

```
hal-common/src/oc/hal/common/embedded/
├── Types.hpp       # Re-exporte ButtonID, EncoderID
├── ButtonDef.hpp   # Définition hardware bouton
├── EncoderDef.hpp  # Définition hardware encodeur
└── GpioPin.hpp     # Configuration GPIO
```

**Dépendances:** `oc/interface/Types.hpp` (framework)

**Problème:** hal-common dépend de framework pour obtenir `ButtonID` et `EncoderID`. Ces types devraient être dans un module plus bas niveau.

### 4.2 hal-teensy

```
hal-teensy/src/oc/hal/teensy/
├── ButtonController.hpp    # : interface::IButton
├── EncoderController.hpp   # : interface::IEncoder
├── UsbMidi.hpp             # : interface::IMidi
├── TeensyGpio.hpp          # : interface::IGpio
├── GenericMux.hpp          # : interface::IMultiplexer
├── Ili9341.hpp             # : interface::IDisplay
├── *Backend.hpp            # : interface::IStorage
├── AppBuilder.hpp          # Builder Teensy-specific
└── Teensy.hpp              # Convenience header
```

**Dépendances:**
- `oc/interface/*` (framework)
- `oc/hal/common/embedded/*` (hal-common)
- `oc/core/Result.hpp` (framework)

**Conforme:** Les implémentations héritent correctement des interfaces avec qualification (`interface::IButton`).

---

## 5. Analyse UI

### 5.1 ui-lvgl

```
ui-lvgl/src/oc/ui/lvgl/
├── IElement.hpp    # Base: accès lv_obj_t*
├── IWidget.hpp     # : IElement + show/hide
├── IComponent.hpp  # : IElement + lifecycle
├── IView.hpp       # : IElement + activate/deactivate
├── IListItem.hpp   # Interface pour listes
├── Bridge.hpp      # Bridge LVGL générique
├── SdlBridge.hpp   # Bridge SDL spécifique
├── Screen.hpp      # Gestion écran
├── Scope.hpp       # Scoped bindings
└── Font*.hpp       # Utilitaires polices
```

**Dépendances:**
- `oc/interface/IDisplay.hpp` (framework)
- `oc/interface/Types.hpp` (framework)
- `oc/core/Result.hpp` (framework)
- `oc/core/struct/Binding.hpp` (framework)

**Problème:** ui-lvgl dépend de `core/struct/Binding.hpp` pour `Scope.hpp`. Couplage avec le système de bindings du framework.

### 5.2 ui-lvgl-components

```
ui-lvgl-components/include/oc/ui/lvgl/
├── widget/         # KnobWidget, ButtonWidget, Label...
├── component/      # ParameterKnob, ParameterEnum...
├── style/          # StyleBuilder
└── theme/          # BaseTheme
```

**Dépendances:** Uniquement `ui-lvgl` (IWidget, IComponent)

**Conforme:** Bonne séparation. Les composants ne dépendent pas directement de framework.

---

## 6. Architecture Cible Proposée

### 6.1 Nouvelle Hiérarchie des Modules

```
Niveau 0: oc::types (NOUVEAU)
          ─────────────────────────────────────────────
          Types primitifs SANS AUCUNE dépendance:
          - ButtonID, EncoderID, TimeProvider
          - ErrorCode, Error, Result<T>
          - ButtonEvent, ButtonCallback, EncoderCallback

          Fichiers: src/oc/types/Types.hpp, Result.hpp
          ─────────────────────────────────────────────
                              │
                              ▼
Niveau 1: oc::interface (PURIFIÉ)
          ─────────────────────────────────────────────
          Interfaces HAL PURES (virtual = 0 uniquement):
          - IButton, IEncoder, IMidi, IDisplay
          - IGpio, IMultiplexer, IStorage, ITransport

          Dépendances: UNIQUEMENT oc::types
          ─────────────────────────────────────────────
                              │
                              ▼
Niveau 2: oc::core
          ─────────────────────────────────────────────
          Logique métier:
          - event/ (Event, EventBus, IEventBus)
          - input/ (InputBinding, Builders)
          - struct/ (Binding)

          Dépendances: oc::types, oc::interface
          ─────────────────────────────────────────────
                              │
                              ▼
Niveau 3: oc::api + oc::context
          ─────────────────────────────────────────────
          - api/: ButtonAPI, EncoderAPI, MidiAPI
          - context/: ContextBase (ex-IContext),
                      ContextManager, IContextSwitcher

          Dépendances: oc::types, oc::interface, oc::core
          ─────────────────────────────────────────────
                              │
                              ▼
Niveau 4: oc::app
          ─────────────────────────────────────────────
          Assemblage: AppBuilder, OpenControlApp
          ─────────────────────────────────────────────
                              │
                              ▼
Niveau 5: oc::impl
          ─────────────────────────────────────────────
          Implémentations null/mock
          Dépendances: oc::interface
          ─────────────────────────────────────────────
```

### 6.2 Changements Requis dans framework/

| Action | Fichier Source | Destination | Raison |
|--------|---------------|-------------|--------|
| **MOVE** | `interface/Types.hpp` | `types/Types.hpp` | Namespace = Chemin |
| **MOVE** | `core/Result.hpp` | `types/Result.hpp` | Type fondamental |
| **MOVE** | `interface/IContext.hpp` | `context/ContextBase.hpp` | Pas une interface pure |
| **MOVE** | `interface/IEventBus.hpp` | `core/event/IEventBus.hpp` | Dépend de Event |
| **MOVE** | `interface/IContextSwitcher.hpp` | `context/IContextSwitcher.hpp` | Lié au context |
| **RENAME** | `IContext` | `ContextBase` | Clarifier que c'est une classe de base |

### 6.3 Nouvelle Structure framework/

```
framework/src/oc/
├── types/              # NOUVEAU - Niveau 0
│   ├── Types.hpp       # ButtonID, EncoderID, TimeProvider, callbacks
│   └── Result.hpp      # ErrorCode, Error, Result<T>
├── interface/          # PURIFIÉ - Niveau 1 (HAL uniquement)
│   ├── IButton.hpp
│   ├── IEncoder.hpp
│   ├── IEncoderHardware.hpp
│   ├── IMidi.hpp
│   ├── IDisplay.hpp
│   ├── IGpio.hpp
│   ├── IMultiplexer.hpp
│   ├── IStorage.hpp
│   └── ITransport.hpp
├── core/               # Niveau 2
│   ├── event/
│   │   ├── Event.hpp
│   │   ├── EventBus.hpp
│   │   ├── IEventBus.hpp   # DÉPLACÉ depuis interface/
│   │   └── Events.hpp
│   ├── input/
│   └── struct/
├── context/            # Niveau 3
│   ├── ContextBase.hpp     # RENOMMÉ depuis IContext
│   ├── IContextSwitcher.hpp # DÉPLACÉ depuis interface/
│   ├── ContextManager.hpp
│   ├── APIs.hpp
│   └── Requirements.hpp
├── api/                # Niveau 3
├── app/                # Niveau 4
├── impl/               # Niveau 5
├── state/
├── log/
├── time/
└── Config.hpp
```

---

## 7. Impact sur les Autres Repos

### 7.1 hal-common

**Changement:** Importer depuis `oc/types/Types.hpp` au lieu de `oc/interface/Types.hpp`

```cpp
// AVANT
#include <oc/interface/Types.hpp>

// APRÈS
#include <oc/types/Types.hpp>
```

### 7.2 hal-teensy

**Changements:**
1. Importer `oc/types/Result.hpp` au lieu de `oc/core/Result.hpp`
2. Importer `oc/types/Types.hpp` au lieu de `oc/interface/Types.hpp`

### 7.3 ui-lvgl

**Changements:**
1. Importer depuis `oc/types/`
2. `Scope.hpp` - revoir la dépendance vers `core/struct/Binding.hpp`

### 7.4 Exemples

Mettre à jour les includes pour refléter la nouvelle structure.

---

## 8. Validation de la Cohérence

### 8.1 Test: "Où va ce nouveau fichier?"

| Nouveau Fichier | Réponse | Justification |
|-----------------|---------|---------------|
| `MidiChannel` (type) | `oc/types/` | Type primitif sans dépendance |
| `ISerial` (interface HAL) | `oc/interface/` | Contrat HAL pur |
| `SerialBinding` (logique) | `oc/core/input/` | Logique de binding |
| `SerialAPI` (façade) | `oc/api/` | Façade utilisateur |
| `MockSerial` (mock) | `oc/impl/` | Implémentation test |

### 8.2 Test: Dépendances Valides

```
✅ types/ → (rien)
✅ interface/ → types/
✅ core/ → types/, interface/
✅ api/ → types/, interface/, core/
✅ context/ → types/, interface/, core/
✅ app/ → tout
✅ impl/ → interface/

❌ interface/ → core/ (INTERDIT)
❌ types/ → interface/ (INTERDIT)
```

---

## 9. Plan de Migration

### Phase 1: Créer oc/types/
1. Créer `src/oc/types/Types.hpp` avec ButtonID, EncoderID, callbacks
2. Créer `src/oc/types/Result.hpp` avec ErrorCode, Result<T>
3. Mettre à jour tous les includes dans framework

### Phase 2: Purifier oc/interface/
1. Déplacer IContext → context/ContextBase.hpp
2. Déplacer IEventBus → core/event/IEventBus.hpp
3. Déplacer IContextSwitcher → context/IContextSwitcher.hpp
4. Supprimer les dépendances vers core/ et api/

### Phase 3: Mettre à jour les HALs
1. hal-common: nouveaux includes
2. hal-teensy: nouveaux includes

### Phase 4: Mettre à jour ui-lvgl
1. Nouveaux includes
2. Revoir Scope.hpp

### Phase 5: Tests et validation
1. Compiler tous les repos
2. Exécuter les tests framework
3. Compiler tous les exemples

---

## 10. Références Architecturales

### Clean Architecture (Robert C. Martin)
> "The Dependency Rule: Source code dependencies must point only inward, toward higher-level policies."

**Application:** Les types primitifs (oc/types) sont au centre. Les interfaces HAL dépendent uniquement des types. La logique métier dépend des interfaces.

### Interface Segregation Principle
> "No client should be forced to depend on methods it does not use."

**Application:** IContext actuel viole ISP car il inclut des méthodes concrètes et des dépendances vers api/. La solution est de le renommer en ContextBase pour clarifier sa nature.

### Package Cohesion Principles
> "Classes in a package should be closed together against the same kinds of changes."

**Application:** Séparer les types primitifs (stables, changent rarement) des interfaces HAL (peuvent évoluer avec le hardware) des implémentations (changent souvent).

---

*Document généré le 2026-01-20*
