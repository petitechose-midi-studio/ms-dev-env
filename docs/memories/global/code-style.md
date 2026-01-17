# Code Style & Conventions

> **Référence officielle** pour midi-studio (Core & Bitwig Plugin)
> Dernière mise à jour: 2026-01-06

## Documentation complète

Pour les guides tutoriels détaillés, voir `midi-studio/core/docs/`:
- `STATE_MANAGEMENT.md` - Signals et state réactif
- `HOW_TO_ADD_WIDGET.md` - Création de widgets LVGL
- `HOW_TO_ADD_HANDLER.md` - Input bindings
- `HOW_TO_ADD_VIEW.md` - Vues complètes
- `HOW_TO_ADD_OVERLAY.md` - Overlays modaux

---

---

## 1. Nommage

| Élément | Convention | Exemple |
|---------|------------|---------|
| Classes | `PascalCase` | `BitwigContext`, `TransportBar` |
| Interfaces | `I` + `PascalCase` | `IContext`, `IView`, `IComponent` |
| Structs | `PascalCase` | `ParameterSlot`, `Requirements` |
| Enums | `PascalCase` (sans préfixe contextuel) | `OverlayType`, `ViewType` |
| Enum values | `SCREAMING_SNAKE_CASE` | `REMOTE_CONTROLS`, `PAGE_SELECTOR` |
| Fonctions/Méthodes | `camelCase` | `initialize()`, `getValue()` |
| **Membres privés** | `snake_case_` (trailing `_`) | `transport_bar_`, `midi_in_indicator_` |
| Variables locales | `snake_case` | `normalized_value`, `selected_index` |
| Constantes | `SCREAMING_SNAKE_CASE` | `MAX_ITEMS`, `MACRO_COUNT` |
| Namespaces | `lowercase` | `bitwig`, `core`, `ui`, `state` |
| Fichiers | `PascalCase.hpp/.cpp` | `BitwigContext.hpp`, `TransportBar.cpp` |

---

## 2. Namespaces

### Structure hiérarchique
```cpp
// Plugin Bitwig
namespace bitwig { }           // Contextes
namespace bitwig::ui { }       // UI components
namespace bitwig::state { }    // State management
namespace bitwig::handler { }  // Input/Host handlers

// Core
namespace core { }             // Contextes
namespace core::ui { }         // UI components
namespace core::state { }      // State management
namespace core::handler { }    // Input handlers
```

### Style C++17 nested
```cpp
// ✅ Correct
namespace bitwig::ui {

class TransportBar { };

}  // namespace bitwig::ui

// ❌ Éviter
namespace bitwig {
namespace ui {
}
}
```

### Closing comment
Toujours indiquer le namespace complet :
```cpp
}  // namespace bitwig::ui
```

---

## 3. Organisation des fichiers

### Structure d'un header (.hpp)
```cpp
#pragma once

/**
 * @file NomDuFichier.hpp
 * @brief Description courte
 *
 * Description détaillée si nécessaire.
 */

// 1. Includes standard C++
#include <cstdint>
#include <memory>
#include <vector>

// 2. Includes externes (framework, libs)
#include <lvgl.h>

#include <oc/context/IContext.hpp>
#include <oc/state/Signal.hpp>

// 3. Includes projet
#include "state/BitwigState.hpp"
#include "protocol/BitwigProtocol.hpp"

namespace bitwig::ui {

// 4. Using declarations (visibles en haut)
using oc::state::Subscription;
using oc::ui::lvgl::IComponent;

/**
 * @brief Description de la classe
 */
class MaClasse : public IComponent {
public:
    // Constructeurs, destructeur
    // Rule of 5 (delete copy)
    // Méthodes publiques

private:
    // Méthodes privées
    // Membres privés
};

}  // namespace bitwig::ui
```

### Séparation des includes
Toujours une ligne vide entre les groupes d'includes.

---

## 4. Structure des classes

```cpp
class MyClass : public IComponent {
public:
    // 1. Types/aliases
    using Callback = std::function<void()>;
    
    // 2. Static constexpr (si applicable)
    static constexpr uint8_t COUNT = 8;
    
    // 3. Constructeurs/Destructeur
    explicit MyClass(lv_obj_t* parent, BitwigState& state);
    ~MyClass() override;
    
    // 4. Rule of 5 (delete copy, optionally delete move)
    MyClass(const MyClass&) = delete;
    MyClass& operator=(const MyClass&) = delete;
    
    // 5. Interface overrides
    void show() override;
    void hide() override;
    
    // 6. Méthodes publiques
    void setValue(float value);

private:
    // 7. Méthodes privées
    void createUI();
    void setupBindings();
    void render();
    
    // 8. Membres privés (snake_case_)
    BitwigState& state_;
    lv_obj_t* container_ = nullptr;
    std::unique_ptr<KnobWidget> knob_;
    std::vector<Subscription> subs_;
};
```

---

## 5. Contextes (IContext)

### Structure standard
```cpp
namespace bitwig {

class BitwigContext : public oc::context::IContext {
public:
    // Déclaration des dépendances (obligatoire si APIs utilisées)
    static constexpr oc::context::Requirements REQUIRES{
        .button = true,
        .encoder = true,
        .midi = true,
        .serial = true
    };

    // Lifecycle
    bool initialize() override;
    void update() override;
    void cleanup() override;
    const char* getName() const override { return "Bitwig"; }

    // Connection (pour DAW contexts)
    bool isConnected() const override;
    void onConnected() override;
    void onDisconnected() override;

private:
    // Factory methods
    void createProtocol();
    void createHostHandlers();
    void createInputHandlers();
    void createViews();

    // Members
    state::BitwigState state_;
    std::unique_ptr<BitwigProtocol> protocol_;
    // ...
};

}  // namespace bitwig
```

---

## 6. Documentation (Doxygen)

### Header de fichier
```cpp
/**
 * @file HandlerInputTransport.hpp
 * @brief Description courte du fichier
 *
 * Description détaillée du pattern, architecture, etc.
 */
```

### Classes
```cpp
/**
 * @brief Description courte de la classe
 *
 * Description détaillée si nécessaire.
 */
class MyClass { };
```

### Constructeurs avec paramètres
```cpp
/**
 * @brief Construct with dependencies
 * @param parent LVGL parent object
 * @param state State reference for reactive bindings
 */
explicit MyClass(lv_obj_t* parent, BitwigState& state);
```

### Méthodes simples (commentaire inline)
```cpp
/// Get the LVGL element
lv_obj_t* getElement() const { return container_; }
```

### Membres (commentaire trailing)
```cpp
Signal<float> value{0.0f};  ///< Normalized value [0.0, 1.0]
```

---

## 7. Formatage (.clang-format)

- **Base**: Google style
- **Indentation**: 4 espaces
- **Ligne max**: 100 caractères
- **Pointeurs**: alignés à gauche (`int* ptr`)
- **Braces**: K&R (même ligne)
- **Namespaces**: compacts

Les fichiers `.clang-format` sont identiques dans Core et Bitwig.

---

## 8. Patterns architecturaux

### Reactive State Pattern
```
Handlers → update State (Signals)
Views → subscribe to State (automatic UI updates)
```

### Handler naming
- `HandlerHost*` : Protocol → State (messages du DAW)
- `HandlerInput*` : Input → Protocol/State (actions utilisateur)

### View naming
- `*View` : Vue principale (RemoteControlsView, MacroView)
- `*Selector` : Liste de sélection (DeviceSelector, TrackSelector)
- `*Widget` : Composant réutilisable (KnobWidget, ButtonWidget)
- `*Bar` : Barre horizontale (TransportBar, TopBar)

---

## 9. Checklist nouveau fichier

- [ ] `#pragma once`
- [ ] Header `@file` + `@brief`
- [ ] Includes groupés et séparés par lignes vides
- [ ] Namespace avec préfixe (`bitwig::`, `core::`)
- [ ] Using declarations au niveau namespace
- [ ] Documentation Doxygen sur la classe
- [ ] Rule of 5 (delete copy)
- [ ] Membres en `snake_case_`
- [ ] Closing comment avec namespace complet

---

## Voir aussi

- `midi-studio/overview.md` - Structure des projets
- `midi-studio/core/docs/` - Guides HOW_TO_* détaillés
