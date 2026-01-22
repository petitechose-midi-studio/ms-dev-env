# Audit Architectural - Open Control Framework (v1)

> **Date:** 2026-01-20
> **Statut:** Itération 1 - Analyse initiale
> **Prochaine étape:** Affiner les détails d'implémentation suspects

---

## Résumé Exécutif

Après analyse exhaustive de ~10 200 lignes de code réparties sur 75+ fichiers, des écarts significatifs ont été identifiés entre les principes du document de design (`open-control-design-guidelines.md`) et l'implémentation actuelle.

**Score de conformité estimé : ~65%**

---

## 1. Violations Identifiées

### 1.1 Namespace ≠ Chemin

| Fichier | Namespace déclaré | Namespace attendu | Sévérité |
|---------|-------------------|-------------------|----------|
| `oc/interface/Types.hpp:7` | `namespace oc` | `oc::interface` | **CRITIQUE** |
| `oc/Config.hpp:29` | `oc::config` | `oc` | Modérée |
| `oc/core/input/InputConfig.hpp:7` | `oc::core` | `oc::core::input` | Modérée |
| `oc/core/struct/Binding.hpp:9` | `oc::core` | `oc::core::struct` | Modérée |

### 1.2 Hiérarchie des Dépendances Inversée

**Interfaces (niveau 1) dépendant de core (niveau 2) :**

| Interface | Dépendance illicite |
|-----------|---------------------|
| `IButton.hpp` | `oc/core/Result.hpp` |
| `IEncoder.hpp` | `oc/core/Result.hpp` |
| `IDisplay.hpp` | `oc/core/Result.hpp` |
| `IMidi.hpp` | `oc/core/Result.hpp` |
| `IMultiplexer.hpp` | `oc/core/Result.hpp` |
| `ITransport.hpp` | `oc/core/Result.hpp` |
| `IEncoderHardware.hpp` | `oc/core/Result.hpp` |
| `IEventBus.hpp` | `oc/core/event/Event.hpp` |

### 1.3 Anti-Pattern 6.1 : IContext

`oc/interface/IContext.hpp` n'est pas une interface pure :
- État privé : `const context::APIs* apis_ = nullptr;`
- ~25 méthodes implémentées (templates et non-virtuelles)
- Dépendances vers `api/`, `context/`, `core/input/`

---

## 2. Décisions Prises

### 2.1 IContext → ContextBase + ContextAPI

**Décision:** Architecture conforme avec séparation des responsabilités.

```
IContext (interface pure, niveau 1)
    ↑
ContextBase (classe de base, niveau 3) ←── ContextAPI (façade fluent)
    ↑
UserContext (code utilisateur)
```

- `IContext` : méthodes virtuelles pures uniquement (lifecycle)
- `ContextBase` : implémentation partielle + injection ContextAPI
- `ContextAPI` : API fluent (`onButton()`, `onEncoder()`, etc.)

### 2.2 Result<T> → oc/types/

**Décision:** Déplacer vers niveau 0 pour supprimer les inversions.

### 2.3 TimeProvider

**Décision:** `oc::TimeProvider` dans `oc/types/Callbacks.hpp` (niveau 0).
Le module `oc::time` consomme ce type.

### 2.4 Tolérance aux exceptions

**Décision:** Corriger toutes les violations, pas d'exception documentée.

---

## 3. Structure Cible

```
src/oc/
├── types/                          # NIVEAU 0
│   ├── Ids.hpp                     # ButtonID, EncoderID, BindingID, ScopeID
│   ├── Callbacks.hpp               # Callbacks, TimeProvider, IsActiveFn
│   ├── Result.hpp                  # Result<T>, ErrorCode, Error
│   └── Event.hpp                   # Event, EventCategoryType, EventType
│
├── interface/                      # NIVEAU 1
│   ├── IButton.hpp
│   ├── IEncoder.hpp
│   ├── IContext.hpp                # Interface PURE
│   ├── IContextSwitcher.hpp
│   ├── IEventBus.hpp
│   ├── IDisplay.hpp
│   ├── IMidi.hpp
│   ├── IStorage.hpp
│   ├── ITransport.hpp
│   ├── IGpio.hpp
│   ├── IMultiplexer.hpp
│   └── IEncoderHardware.hpp
│
├── core/                           # NIVEAU 2
│   ├── event/
│   ├── input/
│   └── struct/
│
├── api/                            # NIVEAU 3
│   ├── ButtonAPI.hpp
│   ├── EncoderAPI.hpp
│   ├── MidiAPI.hpp
│   ├── ContextAPI.hpp              # NOUVEAU
│   ├── ButtonProxy.hpp
│   └── EncoderProxy.hpp
│
├── context/                        # NIVEAU 3
│   ├── ContextBase.hpp             # RENOMMÉ depuis IContext
│   ├── ContextManager.hpp
│   ├── APIs.hpp
│   └── Requirements.hpp
│
├── app/                            # NIVEAU 4
├── impl/                           # NIVEAU 5
├── state/                          # Module autonome
├── time/                           # Module autonome
├── log/                            # Module autonome
├── codec/                          # Module autonome
├── debug/                          # Module autonome
└── util/                           # Module autonome
```

---

## 4. Points à Affiner

- [ ] Détails d'implémentation suspects à investiguer
- [ ] Dépendances circulaires potentielles
- [ ] Cohérence des patterns entre modules
- [ ] Plan de migration détaillé

---

*Document généré lors de l'audit architectural - Itération 1*
