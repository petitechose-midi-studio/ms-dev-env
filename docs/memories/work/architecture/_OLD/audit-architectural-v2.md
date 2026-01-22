# Audit Architectural - Open Control Framework (v2)

> **Date:** 2026-01-20
> **Statut:** Itération 2 - Analyse approfondie des suspects

---

## Synthèse des Suspects Identifiés

### SUSPECT #1 : InputBinding - God Object

**Fichier:** `oc/core/input/InputBinding.hpp` + `.cpp`
**Lignes:** ~180 (header) + ~610 (impl) = **790 lignes**

**Responsabilités mélangées:**
1. Registre des bindings (button + encoder)
2. Gestion des subscriptions EventBus
3. Détection de gestes (long press, double tap, combo)
4. Gestion du latch state
5. Résolution d'autorité (scopes)
6. Tracking d'état des boutons (8 arrays!)

**Code dupliqué interne:**
- `triggerScopedButtonBindings` ≈ `triggerScopedEncoderBindings`
- `triggerGlobalButtonBindings` ≈ `triggerGlobalEncoderBindings`
- `clearButtonScope` ≈ `clearEncoderScope`
- `checkAndTriggerLongPress` pattern ≈ `checkAndTriggerDoubleTap`

**Recommandation:** Extraire en classes séparées:
- `ButtonBindingRegistry` / `EncoderBindingRegistry`
- `GestureDetector` (long press, double tap, combo)
- `LatchManager`

---

### SUSPECT #2 : OpenControlApp - Couplage Temporel

**Fichier:** `oc/app/OpenControlApp.hpp:231-241`

```cpp
// MEMBER DECLARATION ORDER IS CRITICAL FOR SAFE DESTRUCTION
// Required destruction order:
// 1. contexts_      - cleanup() calls clearBindings()
// 2. input_binding_ - destructor calls event_bus_.off()
// 3. event_bus_     - destroyed LAST
```

**Problème:** L'ordre de déclaration des membres impacte la correction du programme.

**Cause racine:** Les composants ont des dépendances implicites via leurs destructeurs.

**Recommandation:**
- Utiliser un pattern de shutdown explicite (`shutdown()` appelé avant destruction)
- Ou encapsuler les dépendances dans un `ServiceContainer` avec ordre de destruction contrôlé

---

### SUSPECT #3 : SysExEvent - Pointeur Non-Owning

**Fichier:** `oc/core/event/Events.hpp:88-95`

```cpp
class SysExEvent : public Event {
    const uint8_t* data;  // Danger: pointeur sans ownership
    uint16_t length;
};
```

**Risque:** Use-after-free si l'émetteur libère les données avant traitement.

**Recommandation:**
- Documenter clairement la lifetime expectation
- Ou utiliser `std::span<const uint8_t>` (C++20)
- Ou copier les données (trade-off performance)

---

### SUSPECT #4 : Duplication ButtonBuilder/EncoderBuilder

**Fichiers:**
- `oc/core/input/ButtonBuilder.hpp`
- `oc/core/input/EncoderBuilder.hpp`

**Éléments dupliqués:**
| Élément | ButtonBuilder | EncoderBuilder |
|---------|---------------|----------------|
| Trait SFINAE | `has_getIsActive` | `has_getIsActive_encoder` |
| Template scope(provider) | lignes 116-123 | lignes 87-94 |
| Membres | `registry_`, `scope_`, `isActive_`, `gestureSet_`, `finalized_` | identique |

**Recommandation:** Extraire un `BuilderBase<Derived>` CRTP ou un trait partagé.

---

### SUSPECT #5 : std::function Usage Intensif

**Statistique:** 32 usages de `std::function` dans les headers.

**Impact embarqué:**
- Chaque `std::function` peut allouer dynamiquement (heap)
- Small Buffer Optimization varie selon le compilateur (~24-32 bytes)
- Lambdas avec captures > SBO → allocation

**Usages critiques:**
- `ButtonCallback = std::function<void(ButtonID, ButtonEvent)>`
- `EventCallback = std::function<void(const Event&)>`
- `ActionCallback = std::function<void()>`
- `IsActiveFn = std::function<bool()>`

**Recommandation:**
- Considérer `etl::delegate` ou équivalent pour l'embarqué
- Ou documenter les contraintes de capture pour éviter les allocations

---

## Hiérarchie des Dépendances - État Réel

```
                    VIOLATIONS
                        ↓
┌─────────────────────────────────────────────────────┐
│  NIVEAU 0 (devrait exister)                         │
│  oc/types/ ← N'EXISTE PAS                           │
│  - ButtonID, EncoderID (actuellement dans interface/)│
│  - Result<T>, ErrorCode (actuellement dans core/)   │
│  - TimeProvider (dupliqué!)                         │
└─────────────────────────────────────────────────────┘
                        ↑
                    INVERSION
                        ↓
┌─────────────────────────────────────────────────────┐
│  NIVEAU 1 : oc/interface/                           │
│  8/13 interfaces dépendent de core/Result.hpp ❌    │
│  IEventBus dépend de core/event/Event.hpp ❌        │
│  Types.hpp déclare namespace oc (pas interface) ❌  │
│  IContext a implémentation + état ❌                │
└─────────────────────────────────────────────────────┘
                        ↑
                   (correct)
                        ↓
┌─────────────────────────────────────────────────────┐
│  NIVEAU 2 : oc/core/                                │
│  Dépend de interface/ ✓                             │
│  InputBinding: God Object à refactorer              │
└─────────────────────────────────────────────────────┘
                        ↑
┌─────────────────────────────────────────────────────┐
│  NIVEAU 3 : oc/api/, oc/context/                    │
│  Structure correcte ✓                               │
└─────────────────────────────────────────────────────┘
                        ↑
┌─────────────────────────────────────────────────────┐
│  NIVEAU 4 : oc/app/                                 │
│  Couplage temporel critique ⚠️                      │
└─────────────────────────────────────────────────────┘
                        ↑
┌─────────────────────────────────────────────────────┐
│  NIVEAU 5 : oc/impl/, oc/hal/                       │
│  Correct ✓                                          │
└─────────────────────────────────────────────────────┘
```

---

## Décisions Confirmées (de v1)

1. **IContext → Interface pure** + **ContextBase** (classe de base dans `context/`) + **ContextAPI** (façade fluent dans `api/`)

2. **Result<T>, ErrorCode** → `oc/types/Result.hpp` (niveau 0)

3. **TimeProvider** → `oc/types/Callbacks.hpp` (niveau 0, définition unique)

4. **Toutes violations à corriger** - Pas d'exceptions documentées

---

## Métriques de la Codebase

| Métrique | Valeur |
|----------|--------|
| Lignes totales | ~10 200 |
| Fichiers source | 75+ |
| Tests | 14 suites |
| Interfaces (I*) | 13 |
| Méthodes virtuelles pures | 69 |
| Usages std::function | 32 |
| God Objects identifiés | 1 (InputBinding) |

---

## Plan de Correction - Priorités

### Phase 1 : Fondations (Critique)
1. Créer `oc/types/` avec Result, ErrorCode, Ids, Callbacks
2. Migrer les interfaces pour utiliser `types/` au lieu de `core/`
3. Extraire Event vers `types/` ou créer `oc/event/` niveau 1

### Phase 2 : IContext (Haute)
1. Créer `IContext` pure dans `interface/`
2. Créer `ContextBase` dans `context/`
3. Créer `ContextAPI` dans `api/`
4. Migrer le code utilisateur vers `ContextBase`

### Phase 3 : Refactoring InputBinding (Moyenne)
1. Extraire `GestureDetector`
2. Séparer button/encoder registries
3. Réduire la complexité cyclomatique

### Phase 4 : Nettoyage (Faible)
1. Supprimer code dupliqué Builders
2. Harmoniser les namespaces (Config, Types, etc.)
3. Documenter les lifetime pour SysExEvent

---

*Document généré lors de l'audit architectural - Itération 2*
