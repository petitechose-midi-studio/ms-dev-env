# Open Control - Design Guidelines

> Document de référence pour les décisions architecturales
> Phase: Design (pas de contraintes legacy)

---

## 1. Objectifs Fondamentaux

### 1.1 Cohérence Absolue
Chaque décision architecturale doit avoir une **justification logique**. Si un fichier, un type, ou une classe est placé quelque part, il doit y avoir une raison claire et défendable.

**Conséquence:** Aucune exception non documentée. Si une exception existe, elle doit être justifiée explicitement.

### 1.2 Patterns Reproductibles
Les conventions établies doivent pouvoir être appliquées de manière **systématique**. Un nouveau contributeur doit pouvoir déduire où placer un nouveau fichier/type sans ambiguïté.

**Test:** "Si je crée un nouveau X, où va-t-il?" doit avoir une réponse unique et évidente.

### 1.3 Extensibilité Sereine
L'architecture doit permettre d'ajouter de nouveaux HALs, de nouvelles fonctionnalités, sans remettre en question les fondations.

**Conséquence:** Les dépendances doivent aller dans un seul sens. Pas de couplage circulaire.

---

## 2. Principes Architecturaux

### 2.1 Dependency Rule (Clean Architecture)
> "Les dépendances du code source ne doivent pointer que vers l'intérieur, vers les politiques de haut niveau."
> — Robert C. Martin, Clean Architecture

**Application:**
```
Types primitifs (aucune dépendance)
       ↑
Interfaces pures (dépendent uniquement des types)
       ↑
Implémentations (dépendent des interfaces)
       ↑
Application (assemble le tout)
```

### 2.2 Interface Segregation Principle (ISP)
> "Aucun client ne devrait être forcé de dépendre de méthodes qu'il n'utilise pas."

**Application:** Les interfaces doivent être petites et focalisées. Une interface HAL ne doit pas inclure de logique framework.

### 2.3 Namespace = Chemin (Convention stricte)
Le namespace C++ **DOIT** refléter exactement le chemin du fichier.

```
src/oc/interface/IButton.hpp → namespace oc::interface
src/oc/core/event/Event.hpp → namespace oc::core::event
```

**Aucune exception.** Si un type doit être dans `namespace oc`, son fichier doit être dans `src/oc/`.

---

## 3. Règles de Placement

### 3.1 Types Primitifs (`oc::types` ou `oc`)
Types fondamentaux sans dépendances:
- `ButtonID`, `EncoderID`
- `ErrorCode`, `Result<T>`
- `TimeProvider`

**Critère:** Utilisé par plusieurs modules, aucune dépendance interne.

### 3.2 Interfaces HAL (`oc::interface`)
Contrats pour l'abstraction hardware:
- `IButton`, `IEncoder`, `IMidi`, `IDisplay`
- `IGpio`, `IMultiplexer`, `IStorage`, `ITransport`

**Critère:**
- Interface pure (virtual = 0)
- Aucune implémentation
- Dépend uniquement des types primitifs

### 3.3 Interfaces Framework (`oc::core::*` ou `oc::context`)
Contrats internes au framework:
- `IEventBus`, `IContextSwitcher`

**Critère:** Peut dépendre de `core/` car fait partie du framework.

### 3.4 Classes de Base (`oc::context` ou `oc::base`)
Classes abstraites avec implémentation partielle:
- `ContextBase` (ex-IContext)

**Critère:** Fournit une implémentation de base, pas une interface pure.

---

## 4. Hiérarchie des Dépendances

```
Niveau 0: oc::types (ou oc/)
    │     Types primitifs, ErrorCode, Result
    │     AUCUNE dépendance interne
    ▼
Niveau 1: oc::interface
    │     Interfaces HAL pures
    │     Dépend uniquement de Niveau 0
    ▼
Niveau 2: oc::core
    │     Logique métier (Event, InputBinding, etc.)
    │     Dépend de Niveau 0 et 1
    ▼
Niveau 3: oc::api, oc::context
    │     Façades et gestion de contexte
    │     Dépend de Niveau 0, 1, 2
    ▼
Niveau 4: oc::app
    │     Assemblage final
    │     Dépend de tout
    ▼
Niveau 5: oc::impl
          Implémentations null/mock
          Dépend de Niveau 1
```

---

## 5. Checklist Nouveau Fichier

Avant de créer un fichier, répondre à:

1. **Quel est son rôle?**
   - [ ] Type primitif → `oc/` ou `oc/types/`
   - [ ] Interface HAL → `oc/interface/`
   - [ ] Logique métier → `oc/core/[module]/`
   - [ ] Façade utilisateur → `oc/api/`
   - [ ] Gestion contexte → `oc/context/`
   - [ ] Assemblage → `oc/app/`
   - [ ] Mock/Null impl → `oc/impl/`

2. **De quoi dépend-il?**
   - [ ] Vérifie que les dépendances respectent la hiérarchie
   - [ ] Pas de dépendance circulaire

3. **Le namespace correspond-il au chemin?**
   - [ ] `src/oc/foo/bar/Baz.hpp` → `namespace oc::foo::bar`

---

## 6. Anti-Patterns à Éviter

### 6.1 Interface avec Implémentation
```cpp
// ❌ MAUVAIS - IContext a des méthodes implémentées
class IContext {
    template <typename ID>
    ButtonBuilder onButton(ID id) { return apis_->button->...; }
private:
    APIs* apis_;  // État!
};
```

### 6.2 Dépendance Inversée
```cpp
// ❌ MAUVAIS - interface/ dépend de core/
// Fichier: oc/interface/IEventBus.hpp
#include <oc/core/event/Event.hpp>
```

### 6.3 Namespace != Chemin
```cpp
// ❌ MAUVAIS - Fichier dans interface/ mais namespace oc
// Fichier: oc/interface/Types.hpp
namespace oc {  // Devrait être oc::interface
    using ButtonID = uint16_t;
}
```

---

## 7. Références

- Robert C. Martin, *Clean Architecture* (2017)
- Robert C. Martin, *SOLID Principles*
- Herb Sutter & Andrei Alexandrescu, *C++ Coding Standards* (2004)

---

*Dernière mise à jour: 2026-01-20*
