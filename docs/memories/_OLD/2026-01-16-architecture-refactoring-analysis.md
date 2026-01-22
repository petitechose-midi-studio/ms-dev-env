# Architecture Refactoring Analysis - midi-studio

**Date:** 2026-01-16  
**Status:** ANALYSE / PROJET - Non destiné à être implémenté immédiatement  
**Tags:** `#architecture` `#refactoring` `#draft` `#icon-collision` `#build-system`

---

## Contexte Initial

### Problème Rencontré
Lors de la mise en place du **système de build unifié** (voir session précédente), un conflit d'includes a été découvert :

```
core/src/ui/font/Icon.hpp        → namespace icon (minuscule)
plugin-bitwig/src/ui/font/icon.hpp → namespace Icon (majuscule)
```

**Cause :** Windows est case-insensitive. Quand les deux include paths sont présents, le compilateur trouve le mauvais fichier selon l'ordre.

### Ce qui a été fait avant cette analyse
1. Refactoring SdlRunner → SdlEnvironment (SRP)
2. Création du système de build unifié (`./build native`, `./build native bitwig`)
3. Suppression de `plugin-bitwig/sdl/CMakeLists.txt` et `build.sh` (obsolètes)
4. Modification de `wasm/CMakeLists.txt` pour supporter APP_PATH

---

## Analyse des Dépendances

### Includes cross-app identifiés

| Pattern | Occurrences | Source | Utilisé par |
|---------|-------------|--------|-------------|
| `<config/App.hpp>` | 20 | core | core + bitwig |
| `<config/PlatformCompat.hpp>` | 16 | core | core + bitwig |
| `<config/InputIDs.hpp>` | 10 | core | core + bitwig |
| `<config/platform-teensy/*>` | 4 | core | core + bitwig |
| `<state/ViewManager.hpp>` | 1 | core | bitwig |
| `<state/OverlayManager.hpp>` | 1 | core | bitwig |
| `<ui/font/CoreFonts.hpp>` | 12 | core | core + bitwig |
| `<ui/ViewContainer.hpp>` | 1 | core | bitwig |
| `<ui/OverlayBindingContext.hpp>` | 5 | core | bitwig |

### Namespace `core::` utilisé par bitwig

```cpp
// Dans BitwigContext.hpp
std::unique_ptr<core::ui::ViewContainer> view_container_;

// Dans BitwigState.hpp
core::state::ViewManager<ViewType, ViewType::REMOTE_CONTROLS> views;
```

### Fichiers d'icônes (source du conflit)

| Fichier | Namespace | Icônes | Usage |
|---------|-----------|--------|-------|
| `core/src/ui/font/Icon.hpp` | `icon` | KNOB, MIDI_CC, NOTE, TRANSPORT_PLAY (5) | Standalone |
| `plugin-bitwig/src/ui/font/icon.hpp` | `Icon` | DEVICE_*, TRACK_*, BROWSER_* (28) | Bitwig |

---

## [PROJET] Plan de Migration Complet

> **STATUS: DRAFT - À AFFINER AVANT IMPLÉMENTATION**
> 
> Ce plan est une réflexion architecturale, pas une action immédiate.

### Structure Proposée

```
midi-studio/
│
├── hw/                              # HARDWARE DEFINITION
│   └── src/
│       ├── Config.hpp               # ex-App.hpp
│       ├── InputIDs.hpp
│       ├── Version.hpp
│       ├── PlatformCompat.hpp
│       └── platform/
│           └── teensy/
│
├── shared/                          # UTILITAIRES PARTAGÉS
│   └── src/
│       ├── state/
│       │   ├── ViewManager.hpp
│       │   └── OverlayManager.hpp
│       └── ui/
│           ├── ViewContainer.hpp
│           ├── OverlayBindingContext.hpp
│           └── TextFonts.hpp        # ex-CoreFonts
│
├── app-standalone/                  # ex-core
│   └── src/
│       ├── icons/
│       │   └── StandaloneIcons.hpp
│       └── ...
│
├── app-bitwig/                      # ex-plugin-bitwig
│   └── src/
│       ├── icons/
│       │   └── BitwigIcons.hpp
│       └── ...
│
└── build
```

### Règles de Dépendance Proposées

```
         ┌──────────┐
         │    hw/   │  ← Définition hardware (aucune dépendance)
         └────┬─────┘
              │
         ┌────▼─────┐
         │ shared/  │  ← Dépend de hw/ + open-control
         └────┬─────┘
              │
    ┌─────────┴─────────┐
    │                   │
┌───▼────┐         ┌────▼───┐
│ app-   │         │ app-   │
│standalone│       │ bitwig │
└────────┘         └────────┘
```

### Impact Estimé (si implémenté)

| Métrique | Valeur |
|----------|--------|
| Fichiers à déplacer | ~16 |
| Fichiers à renommer | ~4 |
| Includes à modifier | ~71 |
| Changements de namespace | ~50+ (si on change `core::` → `shared::`) |

### Problèmes Identifiés avec ce Plan

1. **Namespace `core::`** utilisé partout - changer coûte cher
2. **Dépendances croisées** plus complexes que prévu (CoreFonts dans 12 fichiers, pas 3)
3. **Risque de régression** élevé pour un bénéfice architectural
4. **Temps estimé** : 2-3h minimum

---

## Solution Simple Retenue (à implémenter)

### Principe
Résoudre **uniquement** le conflit d'icônes sans restructuration massive.

### Actions

1. **Renommer les fichiers d'icônes** pour éviter collision de chemins :
   ```
   core/src/ui/font/Icon.hpp → core/src/ui/font/StandaloneIcons.hpp
   plugin-bitwig/src/ui/font/icon.hpp → plugin-bitwig/src/ui/font/BitwigIcons.hpp
   ```

2. **Mettre à jour les includes** (~10 fichiers) :
   ```cpp
   // Avant
   #include "ui/font/Icon.hpp"
   #include "ui/font/icon.hpp"
   
   // Après
   #include "ui/font/StandaloneIcons.hpp"
   #include "ui/font/BitwigIcons.hpp"
   ```

3. **Optionnel** - Harmoniser les namespaces :
   ```cpp
   // Option A: Garder tels quels (icon:: et Icon::)
   // Option B: standalone::icons:: et bitwig::icons::
   ```

### Avantages de la Solution Simple

| Critère | Solution Simple | Migration Complète |
|---------|-----------------|-------------------|
| Fichiers modifiés | ~12 | ~100+ |
| Risque | Faible | Élevé |
| Temps | 10-15 min | 2-3h |
| Résout le problème | Oui | Oui |

---

## État du Build System Unifié

### Ce qui fonctionne
- `./build native` → core compile ✓
- `./build native bitwig` → bitwig compile (après fix icons)
- `./build wasm` → à tester

### Fichiers clés
- `midi-studio/build` - Script wrapper
- `core/sdl/build.sh` - Moteur de build
- `core/sdl/CMakeLists.txt` - CMake paramétré avec APP_PATH
- `core/sdl/app.cmake` - Config core
- `plugin-bitwig/sdl/app.cmake` - Config bitwig

### Modification CMakeLists.txt effectuée
```cmake
# Ordre des includes modifié pour priorité app
target_include_directories(${APP_EXE_NAME} PRIVATE
    ${APP_SRC_DIR}     # App-specific EN PREMIER
    ${CORE_SRC}        # Core headers
    ...
)

# Bloc CORE_SHARED_SOURCES supprimé
# (bitwig n'a plus besoin des .cpp de core/ui/)
```

---

## Décisions à Prendre

### Court terme
- [ ] Implémenter la solution simple (renommage Icon.hpp)
- [ ] Tester `./build native bitwig`
- [ ] Tester `./build wasm`

### Moyen terme (à évaluer)
- [ ] Décider si la restructuration complète vaut le coup
- [ ] Si oui, définir le namespace cible (`core::`, `shared::`, `ms::` ?)
- [ ] Planifier la migration par étapes

---

## Références

- CMakeLists.txt principal : `core/sdl/CMakeLists.txt`
- CMakeLists.txt WASM : `core/sdl/wasm/CMakeLists.txt`
- Build wrapper : `midi-studio/build`
- Project context : `petitechose-audio/project-context.md`
