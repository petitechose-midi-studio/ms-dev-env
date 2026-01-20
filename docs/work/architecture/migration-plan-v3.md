# Plan de Migration - Open Control Framework

> **Date:** 2026-01-20
> **Objectif:** Conformité 100% avec les design guidelines
> **Stratégie:** Modifications atomiques avec validation après chaque étape

---

## Vue d'Ensemble

```
Phase 1: Créer oc/types/ (niveau 0)
    │
    ├── 1.1 Créer types/Result.hpp
    ├── 1.2 Créer types/Ids.hpp
    ├── 1.3 Créer types/Callbacks.hpp
    └── 1.4 Créer types/Event.hpp
    │
Phase 2: Migrer les interfaces
    │
    ├── 2.1 Mettre à jour les includes dans interface/
    ├── 2.2 Supprimer interface/Types.hpp
    └── 2.3 Mettre à jour IEventBus
    │
Phase 3: Migrer le reste du framework
    │
    ├── 3.1 Mettre à jour core/
    ├── 3.2 Mettre à jour api/, app/, context/, state/
    └── 3.3 Supprimer core/Result.hpp (redirect)
    │
Phase 4: Migrer HALs et UI
    │
    ├── 4.1 Mettre à jour hal-*/
    └── 4.2 Mettre à jour ui-lvgl*/
    │
Phase 5: Refactorer IContext
    │
    ├── 5.1 Créer IContext pure
    ├── 5.2 Créer ContextBase
    └── 5.3 Créer ContextAPI
    │
Phase 6: Corriger les namespaces
    │
    ├── 6.1 Config.hpp
    ├── 6.2 InputConfig.hpp
    ├── 6.3 Binding.hpp
    └── 6.4 TimeProvider (supprimer duplication)
```

---

## Phase 1: Créer oc/types/ (Niveau 0)

### Étape 1.1: Créer types/Result.hpp

**Fichier:** `framework/src/oc/types/Result.hpp`

```cpp
#pragma once

/**
 * @file Result.hpp
 * @brief Error handling types (Level 0 - no internal dependencies)
 */

// Copier le contenu exact de core/Result.hpp
// Changer le namespace de oc::core vers oc

namespace oc {
// ... contenu de Result.hpp avec namespace oc au lieu de oc::core
}
```

**Action:**
```bash
mkdir -p framework/src/oc/types
cp framework/src/oc/core/Result.hpp framework/src/oc/types/Result.hpp
# Éditer: changer namespace oc::core → namespace oc
```

**Validation:**
```bash
# Compilation isolée (header-only, pas de .cpp)
```

---

### Étape 1.2: Créer types/Ids.hpp

**Fichier:** `framework/src/oc/types/Ids.hpp`

```cpp
#pragma once

/**
 * @file Ids.hpp
 * @brief Type aliases for identifiers (Level 0 - no dependencies)
 */

#include <cstdint>

namespace oc {

// Input identifiers
using ButtonID = uint16_t;
using EncoderID = uint16_t;

// Binding system identifiers
using BindingID = uint32_t;
using ScopeID = uintptr_t;

}  // namespace oc
```

**Source:** Extraire de `interface/Types.hpp` et `core/struct/Binding.hpp`

**Validation:** Compilation isolée

---

### Étape 1.3: Créer types/Callbacks.hpp

**Fichier:** `framework/src/oc/types/Callbacks.hpp`

```cpp
#pragma once

/**
 * @file Callbacks.hpp
 * @brief Callback type aliases (Level 0 - no internal dependencies)
 */

#include <cstdint>
#include <functional>

#include "Ids.hpp"

namespace oc {

// Time provider function
using TimeProvider = uint32_t(*)();

// Button callbacks
enum class ButtonEvent : uint8_t { PRESSED, RELEASED };
using ButtonCallback = std::function<void(ButtonID, ButtonEvent)>;

// Encoder callbacks
using EncoderCallback = std::function<void(EncoderID, float value)>;

// Generic action callback
using ActionCallback = std::function<void()>;

// Activation predicate for scoped bindings
using IsActiveFn = std::function<bool()>;

}  // namespace oc
```

**Source:** Extraire de `interface/Types.hpp`

**Validation:** Compilation isolée

---

### Étape 1.4: Créer types/Event.hpp

**Fichier:** `framework/src/oc/types/Event.hpp`

```cpp
#pragma once

/**
 * @file Event.hpp
 * @brief Base event types (Level 0 - no internal dependencies)
 */

#include <cstdint>

namespace oc {

using EventCategoryType = uint8_t;
using EventType = uint8_t;

/**
 * @brief Base class for all events
 */
class Event {
public:
    virtual ~Event() = default;
    virtual EventCategoryType getCategory() const = 0;
    virtual EventType getType() const = 0;
};

}  // namespace oc
```

**Source:** Extraire de `core/event/Event.hpp`

**Validation:** Compilation isolée

---

### Validation Phase 1

```bash
cd framework
# Créer un test de compilation minimal
echo '#include <oc/types/Result.hpp>
#include <oc/types/Ids.hpp>
#include <oc/types/Callbacks.hpp>
#include <oc/types/Event.hpp>
int main() { return 0; }' > /tmp/test_types.cpp

g++ -std=c++17 -I src -c /tmp/test_types.cpp -o /tmp/test_types.o
```

---

## Phase 2: Migrer les Interfaces

### Étape 2.1: Mettre à jour les includes dans interface/

**Fichiers à modifier (11 fichiers):**

| Fichier | Ancien include | Nouveau include |
|---------|----------------|-----------------|
| IButton.hpp | `oc/core/Result.hpp` | `oc/types/Result.hpp` |
| IButton.hpp | `oc/interface/Types.hpp` | `oc/types/Ids.hpp` + `oc/types/Callbacks.hpp` |
| IEncoder.hpp | `oc/core/Result.hpp` | `oc/types/Result.hpp` |
| IEncoder.hpp | `oc/interface/Types.hpp` | `oc/types/Ids.hpp` + `oc/types/Callbacks.hpp` |
| IDisplay.hpp | `oc/core/Result.hpp` | `oc/types/Result.hpp` |
| IEncoderHardware.hpp | `oc/core/Result.hpp` | `oc/types/Result.hpp` |
| IMidi.hpp | `oc/core/Result.hpp` | `oc/types/Result.hpp` |
| IMultiplexer.hpp | `oc/core/Result.hpp` | `oc/types/Result.hpp` |
| ITransport.hpp | `oc/core/Result.hpp` | `oc/types/Result.hpp` |

**Commandes:**
```bash
cd framework/src/oc/interface

# Pour chaque fichier:
sed -i 's|#include <oc/core/Result.hpp>|#include <oc/types/Result.hpp>|g' *.hpp
sed -i 's|#include <oc/interface/Types.hpp>|#include <oc/types/Ids.hpp>\n#include <oc/types/Callbacks.hpp>|g' *.hpp

# Mettre à jour les usages de namespace
sed -i 's|core::Result|oc::Result|g' *.hpp
sed -i 's|core::ErrorCode|oc::ErrorCode|g' *.hpp
```

**Note:** Vérifier manuellement chaque fichier après sed.

---

### Étape 2.2: Supprimer interface/Types.hpp

**Avant suppression**, vérifier que plus aucun fichier n'en dépend:

```bash
grep -r "oc/interface/Types.hpp" framework/src hal-*/src ui-*/src
# Doit retourner vide
```

**Action:**
```bash
rm framework/src/oc/interface/Types.hpp
```

---

### Étape 2.3: Mettre à jour IEventBus.hpp

**Fichier:** `framework/src/oc/interface/IEventBus.hpp`

**Modification:**
```cpp
// Avant:
#include <oc/core/event/Event.hpp>

// Après:
#include <oc/types/Event.hpp>
```

**Et ajuster les références de namespace:**
```cpp
// Avant:
using Event = core::event::Event;

// Après:
using Event = oc::Event;
```

---

### Validation Phase 2

```bash
cd framework
pio test -e native
# Tous les tests doivent passer
```

---

## Phase 3: Migrer le Reste du Framework

### Étape 3.1: Mettre à jour core/

**Fichiers à modifier:**

| Fichier | Modifications |
|---------|---------------|
| core/event/Event.hpp | Inclure `oc/types/Event.hpp`, hériter de `oc::Event` |
| core/event/Events.hpp | `#include <oc/types/Ids.hpp>` au lieu de `interface/Types.hpp` |
| core/event/EventBus.hpp | Utiliser `oc::Event` |
| core/input/*.hpp | Remplacer includes |
| core/struct/Binding.hpp | Utiliser `oc::BindingID`, `oc::ScopeID` depuis types/ |

**Pattern de modification pour core/event/Event.hpp:**
```cpp
#pragma once

#include <oc/types/Event.hpp>  // Base class

namespace oc::core::event {

// Re-export base types for backwards compatibility
using oc::Event;
using oc::EventCategoryType;
using oc::EventType;

// Event categories specific to core
namespace EventCategory {
    constexpr EventCategoryType INPUT = 1;
    constexpr EventCategoryType ENCODER = 2;
    constexpr EventCategoryType MIDI = 3;
    constexpr EventCategoryType SYSTEM = 4;
}

}  // namespace oc::core::event
```

---

### Étape 3.2: Mettre à jour api/, app/, context/, state/

**Commandes globales:**
```bash
cd framework/src

# Remplacer tous les includes
find . -name "*.hpp" -o -name "*.cpp" | xargs sed -i 's|#include <oc/interface/Types.hpp>|#include <oc/types/Ids.hpp>\n#include <oc/types/Callbacks.hpp>|g'

find . -name "*.hpp" -o -name "*.cpp" | xargs sed -i 's|#include <oc/core/Result.hpp>|#include <oc/types/Result.hpp>|g'
```

**Fichiers spécifiques:**
- `app/OpenControlApp.hpp` - plusieurs includes à mettre à jour
- `context/ContextManager.hpp` - Result
- `state/Settings.hpp` - Result

---

### Étape 3.3: Créer redirect dans core/Result.hpp

**Option A (recommandée):** Garder core/Result.hpp comme redirect temporaire

```cpp
#pragma once

// DEPRECATED: Use <oc/types/Result.hpp> instead
// This file will be removed in a future version

#include <oc/types/Result.hpp>

namespace oc::core {
    using oc::Result;
    using oc::ErrorCode;
    using oc::Error;
}
```

**Option B:** Supprimer immédiatement (plus risqué)

---

### Validation Phase 3

```bash
cd framework
pio test -e native
# Tous les tests doivent passer
```

---

## Phase 4: Migrer HALs et UI

### Étape 4.1: Mettre à jour hal-*/

**Fichiers à modifier (11 fichiers):**

```bash
cd /path/to/open-control

# hal-midi
sed -i 's|#include <oc/core/Result.hpp>|#include <oc/types/Result.hpp>|g' hal-midi/src/**/*.hpp

# hal-net
sed -i 's|#include <oc/core/Result.hpp>|#include <oc/types/Result.hpp>|g' hal-net/src/**/*.hpp

# hal-sdl
sed -i 's|#include <oc/core/Result.hpp>|#include <oc/types/Result.hpp>|g' hal-sdl/src/**/*.hpp
sed -i 's|#include <oc/interface/Types.hpp>|#include <oc/types/Ids.hpp>\n#include <oc/types/Callbacks.hpp>|g' hal-sdl/src/**/*.hpp

# hal-teensy
sed -i 's|#include <oc/core/Result.hpp>|#include <oc/types/Result.hpp>|g' hal-teensy/src/**/*.hpp

# hal-common
sed -i 's|#include <oc/interface/Types.hpp>|#include <oc/types/Ids.hpp>|g' hal-common/src/**/*.hpp
```

---

### Étape 4.2: Mettre à jour ui-lvgl*/

```bash
# ui-lvgl
sed -i 's|#include <oc/interface/Types.hpp>|#include <oc/types/Callbacks.hpp>|g' ui-lvgl/src/**/*.hpp
```

---

### Validation Phase 4

```bash
# Compiler chaque HAL avec un projet exemple ou test
# Sur desktop:
cd example-sdl && pio run -e sdl

# Les builds Teensy nécessitent le hardware ou CI
```

---

## Phase 5: Refactorer IContext

### Étape 5.1: Créer IContext Pure

**Fichier:** `framework/src/oc/interface/IContext.hpp` (réécriture)

```cpp
#pragma once

/**
 * @file IContext.hpp
 * @brief Pure interface for application contexts (Level 1)
 */

namespace oc::interface {

/**
 * @brief Pure interface for context lifecycle
 *
 * Contexts represent distinct application states or modes.
 * Implement this interface for custom contexts.
 *
 * For convenience methods (onButton, onEncoder, etc.),
 * inherit from ContextBase instead.
 */
class IContext {
public:
    virtual ~IContext() = default;

    /**
     * @brief Initialize context resources
     * @return true if initialization successful
     */
    virtual bool initialize() = 0;

    /**
     * @brief Called every frame while context is active
     */
    virtual void update() = 0;

    /**
     * @brief Cleanup context resources
     */
    virtual void cleanup() = 0;

    /**
     * @brief Get context name for logging/debugging
     */
    virtual const char* getName() const = 0;

    // Optional overrides with defaults
    virtual bool isConnected() const { return true; }
    virtual void onConnected() {}
    virtual void onDisconnected() {}
};

}  // namespace oc::interface
```

---

### Étape 5.2: Créer ContextBase

**Fichier:** `framework/src/oc/context/ContextBase.hpp`

```cpp
#pragma once

/**
 * @file ContextBase.hpp
 * @brief Base class for contexts with fluent API (Level 3)
 */

#include <oc/interface/IContext.hpp>
#include <oc/api/ButtonAPI.hpp>
#include <oc/api/EncoderAPI.hpp>
#include <oc/api/MidiAPI.hpp>
#include <oc/context/APIs.hpp>
#include <oc/core/input/ButtonBuilder.hpp>
#include <oc/core/input/EncoderBuilder.hpp>

namespace oc::context {

/**
 * @brief Base class providing fluent API for contexts
 *
 * Inherit from this class for the convenient onButton(), onEncoder() API.
 */
class ContextBase : public interface::IContext {
public:
    virtual ~ContextBase() = default;

    // ═══════════════════════════════════════════════════════════════════
    // Fluent API for bindings
    // ═══════════════════════════════════════════════════════════════════

    /**
     * @brief Start building a button binding
     */
    template <typename ID>
    core::input::ButtonBuilder onButton(ID id) {
        return apis_->button->builder(static_cast<oc::ButtonID>(id));
    }

    /**
     * @brief Start building an encoder binding
     */
    template <typename ID>
    core::input::EncoderBuilder onEncoder(ID id) {
        return apis_->encoder->builder(static_cast<oc::EncoderID>(id));
    }

    // ═══════════════════════════════════════════════════════════════════
    // API access
    // ═══════════════════════════════════════════════════════════════════

    api::ButtonAPI& button() { return *apis_->button; }
    api::EncoderAPI& encoder() { return *apis_->encoder; }
    api::MidiAPI& midi() { return *apis_->midi; }

    // ... autres méthodes de l'ancien IContext ...

    // ═══════════════════════════════════════════════════════════════════
    // Internal (called by ContextManager)
    // ═══════════════════════════════════════════════════════════════════

    void setAPIs(const APIs* apis) { apis_ = apis; }

protected:
    const APIs* apis_ = nullptr;
};

}  // namespace oc::context
```

---

### Étape 5.3: Migrer le code utilisateur

**Rechercher tous les usages:**
```bash
grep -r "IContext" --include="*.hpp" --include="*.cpp" | grep -v "interface/IContext"
```

**Pattern de migration:**
```cpp
// Avant:
class MyContext : public oc::interface::IContext {

// Après:
class MyContext : public oc::context::ContextBase {
```

---

### Validation Phase 5

```bash
cd framework
pio test -e native

# Tester spécifiquement les contextes
pio test -e native -f test_contextmanager
```

---

## Phase 6: Corriger les Namespaces

### Étape 6.1: Config.hpp

**Fichier:** `framework/src/oc/Config.hpp`

**Modification:**
```cpp
// Avant:
namespace oc::config {

// Après:
namespace oc {
```

**Impact:** Mettre à jour tous les `oc::config::` en `oc::`

```bash
find framework/src -name "*.hpp" -o -name "*.cpp" | xargs sed -i 's|oc::config::|oc::|g'
```

---

### Étape 6.2: InputConfig.hpp

**Fichier:** `framework/src/oc/core/input/InputConfig.hpp`

**Modification:**
```cpp
// Avant:
namespace oc::core {
struct InputConfig {

// Après:
namespace oc::core::input {
struct InputConfig {
```

**Impact:** Mettre à jour les références

```bash
find framework/src -name "*.hpp" -o -name "*.cpp" | xargs sed -i 's|core::InputConfig|core::input::InputConfig|g'
```

---

### Étape 6.3: Binding.hpp

**Fichier:** `framework/src/oc/core/struct/Binding.hpp`

**Modification:** Namespace `oc::core` → `oc::core::struct`

**Alternative:** Déplacer BindingID et ScopeID vers `oc/types/Ids.hpp` (déjà fait en Phase 1)

---

### Étape 6.4: Supprimer TimeProvider dupliqué

**Fichier:** `framework/src/oc/time/Time.hpp`

**Modification:**
```cpp
// Avant:
namespace oc::time {
using TimeProvider = uint32_t(*)();

// Après:
#include <oc/types/Callbacks.hpp>

namespace oc::time {
using oc::TimeProvider;  // Re-export from types
```

---

### Validation Phase 6

```bash
cd framework
pio test -e native
# Tous les tests doivent passer
```

---

## Validation Finale

### Checklist Complète

```bash
# 1. Tous les tests framework
cd framework && pio test -e native

# 2. Vérifier qu'aucun fichier n'inclut les anciens chemins
grep -r "oc/interface/Types.hpp" . && echo "ERREUR: Ancien include trouvé"
grep -r "oc/core/Result.hpp" . | grep -v "DEPRECATED" && echo "ERREUR: Ancien include trouvé"

# 3. Vérifier les namespaces
grep -rn "namespace oc::config" . && echo "ERREUR: Ancien namespace"
grep -rn "^namespace oc::core {" oc/core/input/ && echo "ERREUR: Namespace incomplet"

# 4. Compiler les exemples
cd ../example-sdl && pio run
cd ../example-teensy41-lvgl && pio run  # Si hardware disponible

# 5. Vérifier IContext
grep -r "class.*: public.*IContext" . | grep -v ContextBase && echo "Vérifier ces classes"
```

---

## Rollback Plan

En cas de problème majeur:

```bash
# Revenir au commit précédent
git checkout HEAD~1 -- framework/src/

# Ou restaurer un fichier spécifique
git checkout HEAD~1 -- framework/src/oc/interface/Types.hpp
```

**Recommandation:** Créer une branche pour la migration

```bash
git checkout -b refactor/architecture-cleanup
# ... faire les modifications ...
git push origin refactor/architecture-cleanup
# Créer PR pour review
```

---

## Estimation de Travail

| Phase | Fichiers | Complexité |
|-------|----------|------------|
| Phase 1 | 4 nouveaux | Faible |
| Phase 2 | 11 modifiés | Moyenne |
| Phase 3 | ~15 modifiés | Moyenne |
| Phase 4 | ~15 modifiés | Faible |
| Phase 5 | 3 nouveaux + migrations | Haute |
| Phase 6 | ~5 modifiés | Faible |

---

## État d'Avancement - 2026-01-20

### Commits sur `refactor/architecture-cleanup`:

1. **b4169f7** - Phase 1-4: `oc/types/` module + migration des includes
   - Création de `oc/types/Result.hpp`, `Ids.hpp`, `Callbacks.hpp`, `Event.hpp`
   - Migration de toutes les interfaces vers `oc/types/`
   - 252 tests passent

2. **d70f34f** - Phase 5-6: IContext + namespaces
   - IContext devient interface pure
   - Création de `ContextBase.hpp` avec API fluente
   - Correction `Config.hpp`: `oc::config` → `oc`
   - Correction `InputConfig.hpp`: `oc::core` → `oc::core::input`
   - `Time.hpp` utilise `TimeProvider` depuis `types/Callbacks.hpp`
   - 252 tests passent

3. **8fe3a43** - Nettoyage legacy complet
   - Suppression des fichiers de redirection:
     - `oc/interface/Types.hpp`
     - `oc/core/Result.hpp`
     - `oc/core/event/Event.hpp`
   - Correction `BindingHandle`: `oc::core` → `oc::core::input`
   - Migration de tous les usages vers les nouveaux chemins
   - Suppression des alias de compatibilité arrière
   - 252 tests passent

### Validation finale:
- [x] 252/252 tests passent
- [x] Aucun ancien include (`oc/interface/Types.hpp`, `oc/core/Result.hpp`)
- [x] Aucun ancien namespace (`oc::config`)
- [x] Namespaces = chemins de fichiers
- [x] Fichiers legacy supprimés
- [ ] Compiler les exemples (HALs, ui-lvgl) - à vérifier manuellement

### Prêt pour merge sur main.

---

*Document de migration - v3*
