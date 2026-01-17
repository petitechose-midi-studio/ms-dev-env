# SDL Platform Implementation Plan

**Date**: 2026-01-10 (v2 - après revue durabilité)

## Objectif

Créer un environnement de développement SDL pour `midi-studio/core` permettant :
- Tests sans hardware Teensy
- Debugging complet (breakpoints, watch, call stack)
- Cycle de développement rapide (build ~5s vs 30s+)
- Parité fonctionnelle avec l'environnement Teensy

---

## Décisions architecturales clés

### Pas d'IPlatform

Après analyse, une interface `IPlatform` abstraite n'apporte pas de valeur car :
- **Paradigmes différents** : Teensy (flush direct via IDisplayDriver) vs SDL (compositing custom + driver LVGL intégré)
- **Compositing SDL** : Nécessite accès au SDL_Renderer, ce qui casserait l'abstraction
- **Seulement 2 plateformes** : Pas de pattern commun à extraire

**Solution retenue** : Deux AppBuilders spécialisés (`oc::teensy::AppBuilder` et `oc::sdl::AppBuilder`) qui encapsulent les spécificités de chaque plateforme.

### NullMidiTransport dans framework

Placé dans `framework/src/oc/hal/NullMidiTransport.hpp` pour :
- Réutilisabilité (tests unitaires + SDL + autres)
- Proximité avec l'interface qu'il implémente

---

## État Actuel de la Codebase

### Fichiers Platform-Specific (Teensy uniquement)

| Fichier | Dépendance |
|---------|------------|
| `main.cpp` | `oc::teensy::*`, `micros()` |
| `config/Hardware.hpp` | `oc::teensy::CD74HC4067::Config` |
| `config/HardwareDisplay.hpp` | `oc::teensy::Ili9341Config` |

### Fichiers Déjà Portables

- **Contexts** : `BootContext.hpp`, `StandaloneContext.*` → utilisent `oc::time::millis()`
- **States** : Tous portables
- **Handlers** : Tous portables  
- **UI/Views** : Tous portables (pure LVGL)
- **Fonts** : Portables via `PlatformCompat.hpp`

### Abstractions Framework Existantes

Le framework `open-control` définit des interfaces HAL dans `framework/src/oc/hal/` :
- `IDisplayDriver` - flush, width, height
- `IButtonController` - update, isPressed, setCallback
- `IEncoderController` - update, getPosition, setMode, setCallback
- `IMidiTransport` - sendCC, sendNoteOn, callbacks
- `ISerialTransport` - send, setOnReceive (COBS)
- `IStorageBackend` - read, write, commit
- `IGpio`, `IMultiplexer` - GPIO abstraction
- **`NullMidiTransport`** - No-op MIDI pour tests/desktop (nouveau)

---

## Architecture Cible

### Packages

```
open-control/
├── framework/           # Interfaces HAL + NullMidiTransport
├── ui-lvgl/             # Bridge (embedded) + SdlBridge (desktop)
├── hal-teensy/          # Implémentations Teensy + AppBuilder
└── hal-sdl/             # Implémentations SDL + AppBuilder (nouveau)

midi-studio/core/
├── src/                 # Code partagé + main.cpp Teensy
└── desktop/             # main.cpp SDL + HwSimulator + HwLayout
```

### Pas de main.cpp unifié

Les paradigmes Teensy et SDL sont trop différents pour un main.cpp unifié :
- **Teensy** : Setup/loop pattern Arduino
- **SDL** : Main loop avec compositing, gestion fenêtre, etc.

Chaque plateforme garde son main.cpp spécialisé. La logique métier (contextes, state) est partagée via `AppLogic.hpp`.

---

## Mapping Input SDL

| Hardware | SDL Équivalent |
|----------|----------------|
| Encodeur NAV | Molette souris / flèches haut-bas |
| Bouton NAV | Click molette / Espace |
| Encodeurs MACRO_1-8 | Zones drag souris |
| Boutons MACRO_1-8 | Zones cliquables |
| LEFT_TOP/CENTER/BOTTOM | Q/A/Z |
| BOTTOM_LEFT/CENTER/RIGHT | Zones cliquables |

La configuration du mapping est 100% côté consumer (main.cpp desktop), le mécanisme est dans hal-sdl (InputMapper).

---

## Phases d'Implémentation

### Phase 1 : Fondations (5-8h) ✅ Plan détaillé disponible

Voir `sdl-phase1-implementation-plan` pour le détail complet.

- **framework** : NullMidiTransport
- **ui-lvgl** : SdlBridge (driver SDL LVGL intégré)
- **hal-sdl** : InputMapper, Controllers, AppBuilder
- **consumer** : HwSimulator, HwLayout, MemoryStorage, main.cpp

### Phase 2 : Communication oc-bridge (futur)

```
SDL App ←──TCP:9001/COBS──→ oc-bridge ←──UDP:9000──→ Bitwig
```

- `TcpSerial` : socket TCP pour oc-bridge
- Modifier oc-bridge pour support TCP
- Test communication complète

### Phase 3 : MIDI Desktop (futur)

- `RtMidiTransport` : port MIDI virtuel via RtMidi
- Visible comme "MIDI Studio SDL" dans les DAWs
- Remplace NullMidiTransport pour parité complète

### Phase 4 : Persistence (futur)

- `FileStorage` : sauvegarde JSON sur disque
- Parité avec EEPROM Teensy
- Optionnel si MemoryStorage suffit pour dev

---

## Avantages Debugging Natif

| Fonctionnalité | Teensy | SDL/Native |
|----------------|--------|------------|
| Breakpoints | ❌ | ✅ |
| Step-by-step | ❌ | ✅ |
| Watch variables | ❌ | ✅ |
| Call stack | ❌ | ✅ |
| AddressSanitizer | ❌ | ✅ |
| Valgrind | ❌ | ✅ |
| Profiling | ❌ | ✅ |

---

## Dépendances Externes

| Lib | Usage | Phase |
|-----|-------|-------|
| SDL2 | Fenêtre, events, timer | 1 |
| SDL2_gfx | Dessin HwSimulator | 1 |
| LVGL 9.4.0 | UI (même version) | 1 |
| RtMidi | MIDI virtuel | 3 |
| nlohmann/json (opt) | FileStorage | 4 |

---

## Estimation Effort Total

| Phase | Description | Effort |
|-------|-------------|--------|
| 1 | Fondations (hal-sdl + desktop) | 5-8h |
| 2 | TcpSerial + oc-bridge | 1-2 jours |
| 3 | RtMidi integration | 1 jour |
| 4 | FileStorage | 0.5 jour |
| **Total Phase 1** | **MVP fonctionnel** | **5-8h** |
| **Total complet** | **Parité totale** | **3-5 jours** |

---

## Questions Résolues

| Question | Décision |
|----------|----------|
| IPlatform? | Non - paradigmes trop différents |
| NullMidiTransport où? | framework (réutilisable) |
| Ownership InputMapper? | Raw pointers + documentation |
| HwLayout? | Struct configurable (flexibilité) |
| main.cpp unifié? | Non - trop différent |

## Questions Ouvertes (futures phases)

1. **CI/CD** : Tests automatisés SDL dans GitHub Actions?
2. **Hot reload** : Investiguer rechargement partiel du code?
3. **Multi-window** : Support debugging multi-écrans?
