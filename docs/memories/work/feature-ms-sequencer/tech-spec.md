---
title: 'Step Sequencer Modulaire'
slug: 'step-sequencer'
created: '2026-01-07'
status: 'planned'
stepsCompleted: []
tech_stack:
  - C++17
  - LVGL 9.4.0
  - PlatformIO
  - Teensy 4.1
files_to_modify: []
code_patterns:
  - Signal<T> reactive state (obligatoire)
  - Track FX Chain (INoteFX pipeline)
  - Props-based overlay rendering
  - Fluent input bindings
  - Scheduler avec lookahead (clock)
test_patterns:
  - Unit tests for Track FX
  - Integration tests for engine
---

# Tech-Spec: Step Sequencer Modulaire

**Created:** 2026-01-07

**Status (2026-01-29):** planned. No implementation work is scheduled until the end-user distribution (stable/beta/nightly + ms-manager/ms-updater) is solid.

## Overview

### Problem Statement

MIDI Studio a besoin d'un séquenceur à pas programmable fonctionnant en standalone avec une architecture réutilisable pour le contexte Bitwig. Le séquenceur doit être multi-track (16 pistes), avec une séparation claire entre les **Step Properties** (données par pas) et les **Track FX** (transformations globales), et proposer une expérience cohérente entre les deux contextes d'exécution.

### Solution

Créer un nouveau repo `open-control/note/` contenant la logique pure du séquenceur (moteur, Track FX, scales, clock) avec des interfaces abstraites pour l'output et la synchronisation. L'UI LVGL sera dans `open-control/ui-lvgl-components/`. MIDI Studio Core et Plugin Bitwig consommeront cette bibliothèque avec leurs propres implémentations des interfaces.

**Architecture clé :** Le step séquenceur génère des notes avec leurs propriétés (note, velocity, gate, probability, timing, slide, accent), puis les Track FX transforment ce flux (ratchet, chord, humanize, swing, etc.).

### Scope

**In Scope:**
- Moteur séquenceur multi-track (16 tracks max)
- **7 Step Properties** : Note, Velocity, Gate, Probability, TimeOffset (±50%), Slide, Accent
- **Track FX Chain** : Ratchet, Chord, Scale Quantize, Humanize, Swing, Delay, Transpose
- Micro-timing per-step (±0.5 step)
- Gate > 100% (notes longues débordant sur steps suivants)
- Widget LVGL thémable (8 steps visibles, pagination)
- Overlays : Global (Track FX, sélection propriété) + Per-Step (override propriétés)
- Intégration Core standalone (USB MIDI, clock interne/externe)
- Intégration Plugin Bitwig (Protocol Serial, clock Bitwig, scale Bitwig)
- Mute/Solo par track
- Résolution 24 PPQN
- Voice limiter global (settings)
- MIDI Learn (mode record + per-step)
- **Storage** : SD card (Teensy, SDIO) + file (desktop). Format TBD (JSON draft).
- **GUI Manager PC** : Web GUI (localhost:9001) - in scope v1 mais pas prioritaire
- **Protocol FILE_*** : Commandes transfert fichiers via oc-bridge (chunking Binary)

**Out of Scope (v2+):**
- Modes arpeggiator additionnels (v1 = Up/Down dans Chord FX)
- Presets utilisateur custom (save/load) - Note: presets de BASE inclus en v1
- Modulation Bitwig → Controller
- Step recording depuis Bitwig
- Pattern presets (save/load séquences complètes)
- Undo/Redo complet (v1 = basique ou absent)
- Copy/Paste avancé (v1 = basique)

## Mode Exclusif

Le séquenceur est un **mode exclusif** par rapport au mode Macro :
- **Mode Macro** : Comportement actuel (8 encodeurs = 8 macros CC)
- **Mode Sequencer** : Les 8 encodeurs contrôlent les 8 steps visibles

Un seul mode actif à la fois. Switch via **LEFT_TOP** → Mode Selector (voir `docs/memories/midi-studio/hw-navigation.md`).

## Interactions Hardware

> **Référence :** Voir `docs/memories/midi-studio/hw-navigation.md` pour les patterns universels MIDI Studio.
> **Référence :** Voir `docs/memories/midi-studio/hw-layout.md` pour le schéma physique et IDs.

### Mapping Mode Sequencer (Vue Principale)

| Contrôle | Press | Long Press | Turn |
|----------|-------|------------|------|
| **LEFT_TOP** | Mode Selector | Breadcrumb | — |
| **LEFT_CENTER** | Pattern Config | Track Config | — |
| **LEFT_BOTTOM** | Property Selector | — | — |
| **NAV** | Sequencer Settings | — | Select track (1-16) |
| **OPT** | — | — | Fine tune last touched |
| **MACRO 1-8** | Toggle step | Step Edit + MIDI Learn | Adjust property |
| **BOTTOM_LEFT** | Page ◄ | Copy step | — |
| **BOTTOM_CENTER** | Play/Pause | Stop | — |
| **BOTTOM_RIGHT** | Page ► | Paste step | — |

> **Référence complète :** Voir `docs/memories/midi-studio/hw-sequencer.md` pour les overlays.

### Structure Overlays Séquenceur

```
MODE SEQUENCER (Vue principale)
│
├─── LEFT_TOP press ────► MODE SELECTOR
│
├─── LEFT_CENTER press ─► PATTERN CONFIG (Length, Save/Load/Delete)
├─── LEFT_CENTER long ──► TRACK CONFIG (10 items, 2 pages)
│                         ├──► Scale Selector (3 params)
│                         └──► FX Chain
│                              ├──► Add FX
│                              └──► FX Config
│
├─── LEFT_BOTTOM press ─► PROPERTY SELECTOR (7 props)
│
├─── NAV press ─────────► SEQUENCER SETTINGS
│                         └──► Data Manager
│                              └──► File Picker
│
└─── MACRO long ────────► STEP EDIT (8 params)
```

## Overlays Séquenceur

### Overlay Global (bouton gauche)

Permet de configurer la track active au niveau global :

| Fonction | Description |
|----------|-------------|
| **Sélection propriété** | Choisir quelle propriété les encodeurs modifient (note, velocity, gate, probability, timing) |
| **Track FX Chain** | Voir/modifier la chaîne d'effets de la track |
| **Ajout FX** | Ajouter un effet à la chaîne |
| **Config FX** | Paramétrer un effet (presets, valeurs custom) |
| **Retrait FX** | Retirer un effet de la chaîne |
| **Sélection scale** | Choisir la gamme active pour la track |

Navigation : **Nav encoder** pour se déplacer, **Optical encoder** pour ajuster les valeurs.

### Overlay Per-Step (long press macro)

Permet de configurer un step spécifique (propriétés uniquement, pas de FX) :

| Fonction | Description |
|----------|-------------|
| **Note** | Définir la note MIDI (0-127) |
| **Velocity** | Définir la vélocité (0-127) |
| **Gate** | Définir la durée (0% - 300%+) |
| **Probability** | Définir la probabilité (0-100%) |
| **Time Offset** | Micro-timing (-50% à +50% du step) |
| **Slide** | Activer/désactiver le legato |
| **Accent** | Activer/désactiver l'accent |
| **Clear overrides** | Remettre le step aux valeurs par défaut |

Navigation : **Nav encoder** pour se déplacer, **Optical encoder** pour ajuster les valeurs.

## Système Timing / Mesure

### Calcul Durée Step

```
Durée Step = Longueur Mesure / Nombre de Steps

Exemple : Mesure = 4 temps (1 bar), Steps = 8
→ Durée Step = 4/8 = 0.5 temps = 1 croche
```

### Configuration

| Paramètre | Valeur | Scope |
|-----------|--------|-------|
| **Longueur mesure** | Ex: 4 temps (1 bar) | Global séquenceur |
| **Nombre de steps** | Configurable (8, 16, 32...) | Par track |
| **Steps visibles** | 8 par défaut (= 8 encodeurs) | Configurable |
| **Résolution** | 24 PPQN | Global |

### Gate > 100%

Une note peut déborder sur les steps suivants :
- Gate 100% = note dure exactement 1 step
- Gate 150% = note dure 1.5 steps
- Gate 300% = note dure 3 steps
- NoteOff calculé en **absolu** (pas relatif au step)

### Micro-timing (Time Offset)

Chaque step peut être décalé par rapport à la grille :

| Valeur | Signification |
|--------|---------------|
| `-0.5` | Demi-step en avance |
| `0.0` | Sur la grille (défaut) |
| `+0.5` | Demi-step en retard |

- **Range** : ±50% du step (±0.5)
- **Unité** : Fraction de step
- **UX** : Encodeur en mode "Timing" ajuste cette valeur

```cpp
uint32_t calculateTriggerTick(uint8_t stepIndex, float timeOffset, uint32_t ticksPerStep) {
    int32_t baseTick = stepIndex * ticksPerStep;
    int32_t offsetTicks = static_cast<int32_t>(timeOffset * ticksPerStep);
    return std::max(0, baseTick + offsetTicks);
}
```

## Architecture Mémoire & Storage

### Zones Mémoire Teensy 4.1

| Zone | Taille | Usage |
|------|--------|-------|
| **RAM1 (DTCM)** | 512 KB | Code temps-réel, stack, variables critiques |
| **RAM2 (OCRAM)** | 512 KB | Framebuffer LVGL, DMA buffers |
| **PSRAM** | 8 MB | SequencerState runtime, Undo history |
| **SD card (SDIO)** | (varies) | Persistence : séquences, presets, settings |

### Répartition Séquenceur

```cpp
// PSRAM : Données runtime (volatile)
EXTMEM SequencerState sequencerState;        // ~20 KB
EXTMEM UndoHistory undoHistory;               // ~500 KB

// RAM1 : Temps-réel critique
struct SequencerRuntime {
    uint32_t currentTick = 0;
    NoteEvent pendingNotes[64];
    uint8_t pendingCount = 0;
};
SequencerRuntime runtime;  // ~1 KB

// SD card : Persistence (non-volatile)
// /midi-studio/sequences/*.json
// /midi-studio/presets/fx/*.json
// /midi-studio/presets/chains/*.json
// /midi-studio/settings/global.json
```

### Flow Mémoire

```
Boot → SD card → PSRAM (load)
Edit → PSRAM (runtime)
Save → PSRAM → SD card (persist)
Tick → PSRAM → RAM1 (prepareNextTick) → Output
```

## Persistence (SD card)

### Rationale

- The current core firmware already uses SD card storage via SDIO (non-blocking) for persistence.
- LittleFS persistence was explored historically, but it is not the current direction for the product.

### First boot / init (Teensy)

```cpp
#include <SD.h>

// Teensy 4.1 built-in SDIO
static constexpr int SD_CS = BUILTIN_SDCARD;

bool initStorage() {
    if (!SD.begin(SD_CS)) {
        return false;
    }

    // Create directory structure (best-effort)
    if (!SD.exists("/midi-studio")) SD.mkdir("/midi-studio");
    if (!SD.exists("/midi-studio/sequences")) SD.mkdir("/midi-studio/sequences");
    if (!SD.exists("/midi-studio/presets")) SD.mkdir("/midi-studio/presets");
    if (!SD.exists("/midi-studio/presets/fx")) SD.mkdir("/midi-studio/presets/fx");
    if (!SD.exists("/midi-studio/presets/chains")) SD.mkdir("/midi-studio/presets/chains");
    if (!SD.exists("/midi-studio/settings")) SD.mkdir("/midi-studio/settings");
    if (!SD.exists("/midi-studio/backup")) SD.mkdir("/midi-studio/backup");

    return true;
}
```

### Performance notes

- Debounce auto-save writes; keep the UI loop deterministic.
- Prefer atomic replace (write `*.tmp`, then rename) to reduce corruption risk.

### Presets de Base (générés en code)

Au premier boot, le firmware génère les presets de base :

```cpp
void createDefaultPresets() {
    // FX Presets
    writeJsonIfNotExists("/midi-studio/presets/fx/ratchet_x2.json",
        R"({"type":"ratchet","divisions":2,"decay":0})");
    writeJsonIfNotExists("/midi-studio/presets/fx/ratchet_x4.json",
        R"({"type":"ratchet","divisions":4,"decay":0.2})");
    writeJsonIfNotExists("/midi-studio/presets/fx/swing_medium.json",
        R"({"type":"swing","amount":0.33})");
    writeJsonIfNotExists("/midi-studio/presets/fx/humanize_subtle.json",
        R"({"type":"humanize","velocity":0.05,"timing":0.03})");
    // ... autres presets
}

void createDefaultSettings() {
    writeJsonIfNotExists("/midi-studio/settings/global.json",
        R"({"voiceLimit":16,"defaultBpm":120})");
}
```

### Structure Fichiers

```
/midi-studio/
├── sequences/
│   ├── pattern_01.json
│   ├── pattern_02.json
│   └── ...
├── presets/
│   ├── fx/
│   │   ├── ratchet_x2.json      (généré au 1er boot)
│   │   ├── ratchet_x4.json      (généré au 1er boot)
│   │   ├── swing_medium.json    (généré au 1er boot)
│   │   └── user_custom.json     (créé par utilisateur)
│   └── chains/
│       └── techno_lead.json
├── settings/
│   └── global.json              (généré au 1er boot)
└── backup/
    └── autosave.json
```

### Format JSON (exemple séquence)

```json
{
  "name": "Techno Lead",
  "bpm": 128,
  "measureLength": 4,
  "tracks": [
    {
      "channel": 1,
      "enabled": true,
      "solo": false,
      "resolution": "sixteenth",
      "division": "binary",
      "direction": "forward",
      "offset": 0,
      "scale": { "name": "Minor", "root": 0 },
      "fxChain": [
        { "type": "swing", "amount": 0.33 },
        { "type": "humanize", "velocity": 0.1, "timing": 0.05 }
      ],
      "pattern": {
        "name": "Lead A",
        "length": 16,
        "steps": [
          { "enabled": true, "note": 60, "velocity": 100, "gate": 0.8 },
          { "enabled": false },
          { "enabled": true, "note": 62, "velocity": 90, "gate": 0.5, "slide": true }
        ]
      }
    }
  ]
}
```

**Note :** Le pattern est maintenant un objet imbriqué dans la track, contenant uniquement les données (name, length, steps). Les paramètres de playback (resolution, division, direction, offset) sont au niveau track.

### Comportement Contextes

- **Standalone** : État chargé depuis SD card au boot → PSRAM
- **Bitwig** : Même état, Bitwig y accède via Protocol
- **Arrêt Bitwig** : Séquenceur continue avec son état PSRAM
- **Save** : PSRAM → SD card (auto-save ou manuel)

## GUI Manager (PC)

### Architecture

```
┌─────────────────────────────────────────────────────────┐
│           MIDI Studio Manager (Web GUI)                 │
│              http://localhost:9001                      │
├─────────────────────────────────────────────────────────┤
│  - Liste fichiers (tree view)                           │
│  - Preview JSON (BPM, tracks, steps)                    │
│  - Sélection multiple                                   │
│  - Download vers PC                                     │
│  - Upload depuis PC (drag & drop)                       │
│  - Suppression                                          │
│  - Espace disque utilisé/libre                          │
└─────────────────────────────────────────────────────────┘
                         │
                         ▼ HTTP REST API
┌─────────────────────────────────────────────────────────┐
│                     oc-bridge                           │
│         UDP:9000 (Bitwig) + HTTP:9001 (GUI)             │
└─────────────────────────────────────────────────────────┘
                         │
                         ▼ Binary Protocol
                    [ Teensy 4.1 ]
```

### Protocol : Commandes FILE_*

| Commande | Description |
|----------|-------------|
| `FILE_LIST <path>` | Liste les fichiers d'un répertoire |
| `FILE_READ <path>` | Lit le contenu d'un fichier (JSON) |
| `FILE_WRITE <path> <data>` | Écrit un fichier |
| `FILE_DELETE <path>` | Supprime un fichier |
| `FILE_INFO` | Retourne espace total/utilisé/libre |

### REST API (oc-bridge HTTP:9001)

| Endpoint | Méthode | Description |
|----------|---------|-------------|
| `/api/files?path=/sequences` | GET | Liste fichiers |
| `/api/files/sequences/pattern_01.json` | GET | Lit fichier |
| `/api/files/sequences/pattern_01.json` | PUT | Écrit fichier |
| `/api/files/sequences/pattern_01.json` | DELETE | Supprime |
| `/api/storage` | GET | Info espace disque |

### Technologies GUI

- **Frontend** : Web (React ou Svelte) servi par oc-bridge
- **Accès** : Navigateur sur `http://localhost:9001`
- **Pas d'installation** : oc-bridge sert les fichiers statiques

## Context for Development

### Codebase Patterns

**Patterns existants à suivre :**
- `Signal<T>` pour état réactif (subscriptions RAII)
- `DerivedSignal` pour valeurs calculées
- `SignalWatcher` pour coalescing multi-signal
- Props pattern pour overlays stateless
- Fluent input bindings : `onButton(X).press().scope(S).then(fn)`
- Three-layer separation : Handlers → State → Views
- Interfaces abstraites pour découplage (IClockSource, ISequencerOutput)

**Nouveaux patterns introduits :**
- `INoteFX` pipeline avec `process(input, output, context)`
- `FXChain` configurable et ordonnée (par track)
- `NoteEvent` comme unité de traitement dans le pipeline FX
- **Séparation Step Properties / Track FX** : les steps contiennent les données, les FX transforment le flux
- `NoteScheduler` avec lookahead pour timing précis (humanize bipolaire, delay)

### Interfaces Principales

#### IClockSource
```cpp
namespace oc::note::clock {
struct IClockSource {
    virtual bool isPlaying() const = 0;
    virtual float getBPM() const = 0;
    virtual uint32_t getCurrentTick() const = 0;
    virtual ~IClockSource() = default;
};
}
```

#### ISequencerOutput
```cpp
namespace oc::note::sequencer {
struct ISequencerOutput {
    virtual void sendNoteOn(uint8_t channel, uint8_t note, uint8_t velocity) = 0;
    virtual void sendNoteOff(uint8_t channel, uint8_t note, uint8_t velocity = 0) = 0;
    virtual void sendCC(uint8_t channel, uint8_t cc, uint8_t value) = 0;
    virtual ~ISequencerOutput() = default;
};
}
```
**Note :** `sendNoteOff` inclut velocity pour compatibilité avec `IMidiTransport` existant. Défaut = 0 (ou valeur NoteOn si pertinent).

#### IScaleProvider
```cpp
namespace oc::note::scale {
struct IScaleProvider {
    /// @return Current scale, or nullptr if no constraint
    virtual const Scale* getCurrentScale() const = 0;
    virtual ~IScaleProvider() = default;
};
}
```
**Usage :** Bitwig implémente `IScaleProvider` pour fournir la scale du projet au séquenceur Core.

#### INoteFX (Track FX Pipeline)
```cpp
namespace oc::note::fx {

struct NoteEvent {
    uint8_t note;
    uint8_t velocity;
    uint8_t channel;
    float gate;              // 0.0+ (peut dépasser 1.0)
    int32_t tickOffset;      // Offset relatif (pour ratchet, delay)
    bool slide;
    bool accent;
};

struct FXContext {
    uint32_t ticksPerStep;
    float bpm;
    const scale::Scale* scale;  // nullptr si pas de contrainte
};

struct INoteFX {
    virtual const char* name() const = 0;
    virtual void process(
        const std::span<const NoteEvent>& input,
        std::vector<NoteEvent>& output,
        const FXContext& context
    ) = 0;
    virtual ~INoteFX() = default;
};

}  // namespace oc::note::fx
```

**Note :** Les Track FX ne connaissent pas les steps individuels. Ils transforment un flux de `NoteEvent` généré par le séquenceur.

### Files to Reference

| File | Purpose |
| ---- | ------- |
| `open-control/framework/src/oc/state/Signal.hpp` | Pattern Signal pour état réactif |
| `open-control/framework/src/oc/core/input/ButtonBuilder.hpp` | Fluent API pour bindings |
| `midi-studio/core/src/state/CoreState.hpp` | Structure état existante |
| `midi-studio/core/src/ui/macro/MacroEditOverlay.hpp` | Pattern overlay existant |
| `midi-studio/core/docs/HOW_TO_ADD_HANDLER.md` | Guide création handler |
| `midi-studio/core/docs/HOW_TO_ADD_OVERLAY.md` | Guide création overlay |
| `open-control/hal-teensy/src/oc/teensy/UsbMidi.hpp` | Interface USB MIDI existante |
| `midi-studio/plugin-bitwig/src/handler/input/ViewSwitcherInputHandler.cpp` | Pattern switch mode avec overlay |
| `midi-studio/plugin-bitwig/src/state/ViewManager.hpp` | Pattern ViewManager multi-vues |

### Memory References

| Doc | Purpose |
| --- | ------- |
| `docs/memories/midi-studio/hw-layout.md` | Schéma physique contrôleur, IDs boutons/encodeurs |
| `docs/memories/midi-studio/hw-mapping-template.md` | Template pour définir mappings par écran/overlay |
| `docs/memories/midi-studio/hw-navigation.md` | Patterns navigation universels (LEFT_TOP escape, NAV confirm, OPT fine tune) |
| `docs/memories/midi-studio/hw-sequencer.md` | Mappings séquenceur (overlays, pagination, modifiers) |

### Technical Decisions

**1. Localisation du code séquenceur**
- Décision : Nouveau repo `open-control/note/` (pas dans midi-studio)
- Raison : Réutilisable par tout projet OpenControl, agnostique hardware

**2. Namespaces**
- `oc::note::sequencer` - Moteur, TrackState, StepState
- `oc::note::fx` - INoteFX, FXChain, tous les Track FX
- `oc::note::scale` - Scale, ScaleRegistry, Transposer
- `oc::note::clock` - IClockSource, implémentations

**3. Résolution horloge**
- Décision : 24 PPQN
- Raison : Standard MIDI Clock, compatible hardware externe

**4. Architecture Step Properties + Track FX**
- Décision : Séparation claire entre données (Step) et transformations (FX)
- Raison : Clarté conceptuelle, proche de l'état de l'art (Bitwig, Ableton)
- **Step Properties** : 7 propriétés par step (note, velocity, gate, probability, timeOffset, slide, accent)
- **Track FX Chain** : Chaîne ordonnée configurable par track, transforme le flux de notes
- **Pas de FX per-step** : Les FX s'appliquent à toute la track

**5. Multi-track**
- Décision : 16 tracks max, canal MIDI par défaut = index track
- Raison : Correspond aux 16 canaux MIDI, filtrage facile côté Bitwig
- **Playback** : Toutes les tracks `enabled=true` jouent simultanément (stack)
- **Longueur** : Chaque track a sa propre longueur (indépendante)
- **Édition** : Une seule track active pour édition (`activeTrackIndex`)
- **Mute/Solo** : `enabled=false` pour mute, `solo=true` pour solo (seules les tracks solo jouent)

**6. Gate > 100%**
- Décision : Supporté, NoteOff calculé en absolu
- Raison : Permet notes longues, legato naturel

**7. Contexte Bitwig**
- Décision : Bitwig accède au séquenceur Core via Protocol, pas de duplication
- Raison : État persisté sur contrôleur, continuité quand Bitwig s'arrête

**8. Voice Limiter**
- Décision : Limiter global dans les settings, pas per-track
- Raison : Évite saturation MIDI avec multi-track + notes longues + FX génératifs
- Valeur par défaut : 16 voix simultanées

**9. MIDI Learn**
- Décision : Deux modes de saisie des notes
- **Mode Record** : Appui sur Record → chaque note reçue affecte le step courant et passe au suivant
- **Mode Per-Step** : Long press sur macro (en mode pitch) + note externe → affecte ce step
- **Note** : MIDI Learn écoute MIDI IN, séquenceur fait MIDI OUT → pas de conflit

**10. Organisation Repo**
- Décision : `open-control/note/` est un **repo git séparé** (pas un submodule)
- Raison : Submodules difficiles à maintenir, repo séparé plus simple
- Intégration : Référencé comme dépendance dans `platformio.ini` de midi-studio/core

**11. SequencerState et CoreState**
- Décision : **Injection de dépendance** (DI) - SequencerState séparé de CoreState
- Raison : SequencerState en PSRAM, CoreState en RAM1 - séparation mémoire claire
- Pattern : CoreState reçoit une référence à SequencerState, ou les deux sont injectés séparément dans les handlers

**12. FXChain Ordre**
- Décision : **Configurable par l'utilisateur**
- Comportement : Chaque ajout se place après le dernier FX inséré
- UX : Possibilité de réordonner (détails dans Phase Layout)

**13. Clock Source Priorité**
- Décision : **Auto-détection avec override dans settings**
- Priorité par défaut : MIDI Clock externe > Bitwig (si connecté) > Interne
- Modifiable : Settings séquenceur permettent de forcer une source

**14. Voice Limiter Algorithme**
- Décision : **Oldest first, global**
- Tracking : Global (pas par channel)
- Algorithme : Note stealing sur la plus ancienne note active (premier NoteOn non résolu)

**15. Accent Comportement**
- Décision : **Configurable** dans SequencerSettings
- Défaut : +50% velocity
- Clamp : Velocity max 127
- Formule : `velocity = min(127, velocity * (1 + accentBoost))`

**16. Slide (Legato) Implémentation**
- Décision : **Overlap** - NoteOn arrive AVANT NoteOff de la note précédente
- Timing : NoteOff retardé de ~10ms après le NoteOn suivant
- Standard MIDI : Les synthés mono détectent l'overlap et ne re-triggent pas l'enveloppe

**17. Clock Architecture**
- Décision : **Push + Scheduler avec lookahead**
- La clock pousse les ticks via `onTick(uint32_t tick)`
- Le moteur pré-calcule 2 steps à l'avance
- Notes schedulées dans une priority queue triée par tick
- Permet : humanize bipolaire, gate > 100%, delay FX

**18. Swing Comportement**
- Décision : **Timing only** sur off-beats (steps impairs)
- Paramètre : `amount` (0.0 - 1.0)
- Formule : off-beat décalé de `amount * 0.5 * ticksPerStep`
- Pas d'effet sur velocity en v1

**19. HumanizeFX**
- Décision : **Bipolaire** (±timing)
- Possible grâce au scheduler lookahead
- Paramètres : `velocityVar`, `timingVar`, `gateVar` (0.0 - 1.0)

**20. DelayFX Paramètres**
- `delayTicks` : Décalage en ticks
- `repeats` : Nombre de répétitions (1-8)
- `velocityDecay` : Atténuation velocity par répétition (0.0-1.0)
- `gateDecay` : Optionnel, atténuation gate (0.0-1.0, défaut 0 = gate identique)

**21. Scale Source**
- Décision : **Track.scale** est la référence unique
- ScaleQuantizeFX utilise `track.scale` (pas de scale propre au FX)

**22. Playhead Multi-track**
- Décision : **Modulo** - `globalStep % track.length`
- Offset/rotation du pattern reporté en v2

**23. Signal<T>**
- Décision : **Obligatoire** (pas optionnel)
- open-control/note dépend de oc::state::Signal

**24. Auto-save**
- Décision : **Event + timeout**
- Utilise AutoPersist du framework
- Save quand système stabilisé (pas de modification pendant N secondes)

**25. Hiérarchie Données**
- **Projet** : Contient séquences + settings globaux
- **Séquence** : Contient patterns + FX chain
- **Pattern** : Juste les steps (configuration des pas)

**26. FXType Enum (pas de std::string)**
```cpp
enum class FXType : uint8_t {
    Ratchet,
    Chord,
    ScaleQuantize,
    Humanize,
    Swing,
    Delay,
    Transpose
};
```

**27. Bitwig Accès**
- Décision : **Accès direct** au SequencerState depuis contexte Bitwig
- Pas via Protocol - le contexte Bitwig a une référence au séquenceur Core
- Peut lire et modifier l'état comme le contexte standalone

**28. MIDI Channel Convention**
- Interne : **0-based** (0-15)
- Affichage : **1-based** (1-16)

**29. Séparation Pattern / Track**
- Décision : **Pattern = données pures**, **Track = configuration playback**
- **PatternState** contient : name, length, steps[]
- **TrackState** contient : channel, mute, solo, resolution, division, direction, offset, scale, fxChain, pattern
- Raison : Clarté conceptuelle, pattern réutilisable (v2), correspond au standard industrie (Bitwig, Ableton)
- V1 : Pattern embarqué dans Track (`TrackState.pattern`)
- V2 potentiel : `PatternBank` avec références par ID

**30. Architecture BPM Deux Niveaux**
- Décision : **Default BPM** (settings globaux) + **Session BPM** (état runtime)
- `SequencerSettings.defaultBpm` : Persisté, valeur de démarrage
- `SequencerState.bpm` : Tempo courant, modifiable en live
- Reset BPM : Copie defaultBpm → bpm
- Raison : Permet de définir un tempo par défaut tout en autorisant des variations par session

## Implementation Plan

### Phase 1 : Architecture Core (open-control/note/)

**À définir dans Step 2 : Investigation approfondie**
- Structure détaillée des fichiers
- Interfaces complètes
- Tests unitaires

### Phase 2 : UI (open-control/ui-lvgl-components/)

**À définir dans Step 2**
- StepSequencerWidget
- StepWidget
- Theme system

### Phase 3 : Intégration MIDI Studio

**À définir après Phase Layout**
- Handlers navigation
- Overlays
- Bindings hardware

### Tasks

**À compléter dans Step 2 (Investigation)**

### Acceptance Criteria

**À compléter dans Step 3 (Generate)**

## Additional Context

### Dependencies

**open-control/note/ dépend de :**
- C++ STL uniquement (pour portabilité)
- Optionnel : `oc::state::Signal<T>` du framework (pour réactivité)

**NE dépend PAS de :**
- CoreState
- LVGL
- HAL spécifique

**midi-studio/core/ dépend de :**
- `open-control/note/`
- `open-control/ui-lvgl-components/`
- `open-control/hal-teensy/`

### Testing Strategy

**Unit Tests (open-control/note/) :**
- Chaque Track FX individuellement (RatchetFX, ChordFX, etc.)
- FXChain (ordre, bypass)
- Scale contraintes et quantization
- SequencerEngine tick processing
- StepState lazy allocation
- NoteEvent generation depuis StepState

**Integration Tests (midi-studio/core/) :**
- Overlay lifecycle
- Handler bindings
- Multi-track playback simultané
- Clock sync (interne, externe, Bitwig)
- Voice limiter behavior
- MIDI Learn modes

### Notes

**Questions résolues (voir `docs/memories/midi-studio/hw-sequencer.md`) :**
- ✅ Sélectionner une track → NAV turn (1-16)
- ✅ Mute/Solo → Track Config (MACRO 3/4)
- ✅ Switch Macro ↔ Sequencer → LEFT_TOP → Mode Selector
- ✅ Définir longueur → Pattern Config → Length
- ✅ Navigation overlays → Documentée dans `docs/memories/midi-studio/hw-sequencer.md`

**Évolutions futures identifiées :**
- Modes arpeggiator additionnels
- Presets utilisateur
- Pattern presets
- Modulation externe
- Step recording

---

## Annexe : Structure Fichiers Repos

### open-control/note/
```
open-control/note/
├── library.json
├── README.md
└── src/oc/note/
    ├── sequencer/
    │   ├── SequencerEngine.hpp      # Moteur principal, tick processing
    │   ├── SequencerState.hpp       # État global multi-track
    │   ├── SequencerSettings.hpp    # Settings globaux (voice limiter, etc.)
    │   ├── PlaybackTypes.hpp        # Enums Resolution, Division, Direction
    │   ├── StepState.hpp            # État d'un pas (7 propriétés)
    │   ├── PatternState.hpp         # Pattern = données pures (name, length, steps)
    │   ├── TrackState.hpp           # Track = config playback + pattern
    │   ├── NoteEvent.hpp            # Structure événement note (sortie step)
    │   ├── NoteScheduler.hpp        # Priority queue avec lookahead
    │   └── ISequencerOutput.hpp     # Interface sortie MIDI
    ├── fx/
    │   ├── INoteFX.hpp              # Interface Track FX
    │   ├── FXChain.hpp              # Chaîne configurable
    │   ├── FXContext.hpp            # Contexte pour processing
    │   ├── RatchetFX.hpp            # Répétitions rapides
    │   ├── ChordFX.hpp              # Génère accords (remplace MultiNote + Arp)
    │   ├── ScaleQuantizeFX.hpp      # Contraint à la gamme
    │   ├── HumanizeFX.hpp           # Randomisation timing/velocity
    │   ├── SwingFX.hpp              # Groove off-beats
    │   ├── DelayFX.hpp              # Écho avec decay
    │   └── TransposeFX.hpp          # Décalage pitch global
    ├── scale/
    │   ├── Scale.hpp                # Définition d'une gamme
    │   ├── ScaleRegistry.hpp        # Toutes les gammes de base
    │   ├── Transposer.hpp           # Transposition chromatic/scale
    │   └── IScaleProvider.hpp       # Interface provider externe
    └── clock/
        ├── IClockSource.hpp         # Interface horloge
        ├── InternalClock.hpp        # Horloge interne (BPM configurable)
        └── MidiClockReceiver.hpp    # Sync MIDI clock externe
```

### open-control/ui-lvgl-components/ (extension)
```
open-control/ui-lvgl-components/
└── src/oc/ui/lvgl/sequencer/
    ├── StepSequencerWidget.hpp      # Widget complet 8 steps
    ├── StepWidget.hpp               # Un pas individuel
    ├── StepSequencerTheme.hpp       # Thème customisable (couleurs, dimensions)
    └── IStepSequencerCallbacks.hpp  # Callbacks UI → Logic
```

#### StepSequencerTheme (Structure)
```cpp
namespace oc::ui::lvgl::sequencer {
struct StepSequencerTheme {
    // Couleurs
    lv_color_t stepOff = lv_color_hex(0x333333);
    lv_color_t stepOn = lv_color_hex(0x00FF00);
    lv_color_t stepActive = lv_color_hex(0xFFFFFF);  // Playhead
    lv_color_t valueArc = lv_color_hex(0x0088FF);
    lv_color_t background = lv_color_hex(0x1A1A1A);

    // Dimensions
    lv_coord_t stepWidth = 32;
    lv_coord_t stepHeight = 48;
    lv_coord_t stepGap = 4;
    lv_coord_t arcRadius = 12;

    // Typographie
    const lv_font_t* valueFont = &lv_font_montserrat_12;
};
}
```
**Usage :** Core utilise thème standalone, Plugin Bitwig utilise thème aux couleurs Bitwig (orange).

### midi-studio/core/ (intégration)
```
midi-studio/core/src/
├── sequencer/
│   ├── CoreSequencerIntegration.hpp # Lie oc::note à CoreState
│   ├── UsbMidiOutput.hpp            # Impl ISequencerOutput (USB MIDI)
│   ├── InternalClockSource.hpp      # Impl IClockSource (BPM interne)
│   └── ExternalMidiClockSource.hpp  # Impl IClockSource (MIDI clock ext)
├── handler/sequencer/
│   ├── SequencerModeHandler.hpp     # Switch Macro ↔ Sequencer
│   ├── SequencerStepHandler.hpp     # Boutons/encodeurs des pas
│   ├── SequencerGlobalHandler.hpp   # Overlay global
│   ├── SequencerStepOverlayHandler.hpp # Overlay per-step
│   └── SequencerTrackHandler.hpp    # Sélection/gestion tracks
└── ui/sequencer/
    ├── SequencerView.hpp            # Vue principale (utilise widget)
    ├── SequencerGlobalOverlay.hpp   # Overlay config globale
    └── SequencerStepOverlay.hpp     # Overlay config per-step
```

### midi-studio/plugin-bitwig/ (intégration)
```
midi-studio/plugin-bitwig/src/sequencer/
├── BitwigClockSource.hpp            # Impl IClockSource (transport Bitwig)
├── ProtocolSequencerOutput.hpp      # Impl ISequencerOutput (Serial → Bitwig)
└── BitwigScaleProvider.hpp          # Impl IScaleProvider (scale projet Bitwig)
```

---

## Annexe : Structures de Données

### Enums de Playback

```cpp
namespace oc::note::sequencer {

/**
 * @brief Résolution temporelle du playback
 * Définit combien de temps dure chaque step par rapport à la mesure
 */
enum class Resolution : uint8_t {
    Whole = 0,      // 1/1 - Ronde
    Half,           // 1/2 - Blanche
    Quarter,        // 1/4 - Noire (défaut)
    Eighth,         // 1/8 - Croche
    Sixteenth,      // 1/16 - Double croche
    ThirtySecond,   // 1/32 - Triple croche
    SixtyFourth     // 1/64 - Quadruple croche
};

/**
 * @brief Division rythmique (modificateur de résolution)
 */
enum class Division : uint8_t {
    Binary = 0,     // Normal (défaut)
    Dotted,         // Pointé (×1.5)
    Triplet,        // Triolet (×2/3)
    Quintuplet,     // Quintolet (×4/5)
    Septuplet       // Septolet (×4/7)
};

/**
 * @brief Direction de lecture du pattern
 */
enum class Direction : uint8_t {
    Forward = 0,    // Avant (défaut)
    Backward,       // Arrière
    PingPong,       // Aller-retour
    Random          // Aléatoire
};

}  // namespace oc::note::sequencer
```

### StepState (7 propriétés)
```cpp
namespace oc::note::sequencer {

struct StepState {
    bool enabled = false;
    uint8_t note = 60;           // Note MIDI (0-127)
    uint8_t velocity = 100;      // Vélocité (0-127)
    float gate = 1.0f;           // Durée (0.0 - N.0, peut dépasser 1.0)
    float probability = 1.0f;    // Probabilité (0.0 - 1.0)
    float timeOffset = 0.0f;     // Micro-timing (-0.5 à +0.5)
    bool slide = false;          // Legato vers note suivante
    bool accent = false;         // Flag accent (boost velocity configurable)
};

}  // namespace oc::note::sequencer
```

**Taille mémoire :**
- Step : ~12 bytes
- 16 tracks × 64 steps = 1024 steps → ~12 KB

### PatternState (données pures)

```cpp
namespace oc::note::sequencer {

static constexpr uint8_t MAX_STEPS_PER_PATTERN = 64;
static constexpr uint8_t MAX_PATTERN_NAME_LENGTH = 16;

/**
 * @brief Pattern = données pures (steps + length)
 *
 * Séparé de TrackState pour permettre :
 * - Réutilisation de patterns entre tracks (v2)
 * - Save/Load indépendant du contexte de lecture
 * - Clarté conceptuelle (données vs config)
 */
struct PatternState {
    char name[MAX_PATTERN_NAME_LENGTH] = "Pattern";
    uint8_t length = 16;          // Nombre de steps actifs (1-64)
    std::array<StepState, MAX_STEPS_PER_PATTERN> steps;
};

}  // namespace oc::note::sequencer
```

**Note architecture :** Le Pattern contient uniquement les données (steps + length). Les paramètres de lecture (Resolution, Division, Direction, Offset) sont dans TrackState.

### NoteEvent (sortie du séquenceur)
```cpp
namespace oc::note::sequencer {

struct NoteEvent {
    uint8_t note;
    uint8_t velocity;
    uint8_t channel;
    float gate;              // 0.0+ (peut dépasser 1.0)
    int32_t tickOffset;      // Offset relatif en ticks
    bool slide;
    bool accent;
};

}  // namespace oc::note::sequencer
```

### TrackState (configuration playback)

```cpp
namespace oc::note::sequencer {

/**
 * @brief Track = configuration de lecture + référence au pattern
 *
 * La Track définit COMMENT le pattern est joué :
 * - Paramètres de playback (resolution, division, direction, offset)
 * - Routage audio (channel, scale, fxChain)
 * - États de mixage (mute, solo)
 *
 * V1 : Une track = un pattern embarqué
 * V2 : Possibilité de référencer des patterns partagés
 */
struct TrackState {
    // === Routage ===
    uint8_t channel = 0;              // Canal MIDI (0-15, affichage +1)

    // === Mixage ===
    bool enabled = true;              // Mute si false
    bool solo = false;                // Solo mode

    // === Playback config ===
    Resolution resolution = Resolution::Sixteenth;  // 1/16 par défaut
    Division division = Division::Binary;           // Normal
    Direction direction = Direction::Forward;       // Avant
    uint8_t offset = 0;               // Décalage en steps (0-63)

    // === Audio processing ===
    fx::FXChain fxChain;              // Chaîne d'effets de la track
    const scale::Scale* scale = nullptr;  // Scale contrainte (nullable)

    // === Pattern (données) ===
    PatternState pattern;             // V1: pattern embarqué dans la track
};

}  // namespace oc::note::sequencer
```

**Note architecture :** En V1, chaque track contient son propre pattern. En V2, on pourrait avoir un `PatternBank` et les tracks référenceraient des patterns par ID.

### SequencerState
```cpp
namespace oc::note::sequencer {

struct SequencerState {
    std::array<TrackState, 16> tracks;
    uint8_t activeTrackIndex = 0;    // Track en édition
    uint8_t currentStep = 0;         // Playhead position
    bool playing = false;
    float bpm = 120.0f;
    uint8_t measureLength = 4;       // Temps par mesure
};

}  // namespace oc::note::sequencer
```

### SequencerSettings (globaux persistés)

```cpp
namespace oc::note::sequencer {

/**
 * @brief Settings globaux du séquenceur (persistés dans /settings/global.json)
 *
 * Note BPM : Architecture à deux niveaux
 * - defaultBpm (ici) = tempo par défaut au démarrage
 * - SequencerState.bpm = tempo de la session courante (peut être modifié)
 * - Reset BPM dans Sequencer Settings → revient à defaultBpm
 */
struct SequencerSettings {
    float defaultBpm = 120.0f;       // BPM par défaut (20-300)
    uint8_t voiceLimit = 16;         // Max voix simultanées
    float accentBoost = 0.5f;        // Boost velocity accent (+50% défaut)
    // ClockSource défini à l'exécution, pas persisté
};

}  // namespace oc::note::sequencer
```

**Note architecture BPM :**
- `SequencerSettings.defaultBpm` = valeur par défaut, persistée dans settings globaux
- `SequencerState.bpm` = tempo de la session courante, peut être modifié en live
- Reset BPM (dans Sequencer Settings overlay) → copie defaultBpm vers bpm

---

## Annexe : Step Properties

Les 7 propriétés stockées dans chaque step :

| Propriété | Type | Range | Description |
|-----------|------|-------|-------------|
| **enabled** | bool | true/false | Step actif ou non |
| **note** | uint8_t | 0-127 | Note MIDI |
| **velocity** | uint8_t | 0-127 | Vélocité |
| **gate** | float | 0.0 - ∞ | Durée (1.0 = 100%, peut dépasser) |
| **probability** | float | 0.0 - 1.0 | Chance de jouer |
| **timeOffset** | float | -0.5 - +0.5 | Micro-timing (fraction de step) |
| **slide** | bool | true/false | Legato vers note suivante |
| **accent** | bool | true/false | Boost velocity |

---

## Annexe : Track FX Détaillés

Les FX s'appliquent au niveau de la track, transformant le flux de notes.

### RatchetFX
- Type : Generative
- Paramètres : `divisions: uint8_t (2-8), decay: float (0.0-1.0)`
- Comportement : Répète chaque note N fois dans sa durée
- **Presets** : x2, x3, x4, Roll (x8 avec decay rapide)

### ChordFX
- Type : Generative
- Paramètres : `intervals: std::vector<int8_t>, mode: ChordMode`
- Modes : Stack (toutes simultanées), Up, Down, UpDown, Random
- Comportement : Génère accord depuis note source, optionnellement arpégé
- **Presets** : Octave `[0,12]`, Power5 `[0,7]`, Major `[0,4,7]`, Minor `[0,3,7]`, Sus4 `[0,5,7]`, 7th `[0,4,7,10]`

### ScaleQuantizeFX
- Type : Constraint
- Paramètres : `mode: QuantizeMode` (utilise `track.scale` comme référence)
- Modes : Nearest (note la plus proche), Up (note supérieure), Down (note inférieure)
- Comportement : Force les notes à la gamme définie sur la track

### HumanizeFX
- Type : Randomization
- Paramètres : `velocityVar: float, timingVar: float, gateVar: float`
- Range variations : 0.0 - 1.0 (fraction de step pour timing)
- Timing : **Bipolaire** (±) grâce au scheduler lookahead
- **Presets** : Subtle (5%), Medium (15%), Drunk (30%)

### SwingFX
- Type : Timing
- Paramètres : `amount: float (0.0-1.0)`
- Comportement : Décale les **off-beats** (steps impairs : 1, 3, 5, 7)
- Formule : `offset = amount * 0.5 * ticksPerStep`
- Pas d'effet sur velocity en v1
- **Presets** : Light (10%), Medium (33%), Heavy (66%)

### DelayFX
- Type : Timing/Generative
- Paramètres :
  - `delayTicks: uint32_t` - Décalage en ticks
  - `repeats: uint8_t` - Nombre de répétitions (1-8)
  - `velocityDecay: float` - Atténuation velocity (0.0-1.0)
  - `gateDecay: float` - Atténuation gate optionnelle (0.0-1.0, défaut 0)
- Comportement : Écho avec répétitions, velocity décroît, gate identique ou décroît
- **Presets** : Short (1/16), Medium (1/8), Long (1/4), Dotted, Triplet

### TransposeFX
- Type : Pitch
- Paramètres : `semitones: int8_t (-24 à +24)`
- Comportement : Décale toutes les notes

---

## Annexe : Module Scale

### Structure Scale
```cpp
namespace oc::note::scale {
struct Scale {
    const char* name;                    // "Major", "Minor", "Dorian", etc.
    std::array<uint8_t, 12> intervals;   // Quels demi-tons sont dans la gamme
    uint8_t rootNote;                    // Note racine (0-11, C=0)

    /// Contraint une note à la gamme
    uint8_t constrainNote(uint8_t note) const;

    /// Retourne le Nième degré depuis la racine
    uint8_t getDegree(uint8_t degree) const;
};
}
```

### ScaleRegistry - Gammes de Base
| Gamme | Intervalles |
|-------|-------------|
| Major (Ionian) | 0, 2, 4, 5, 7, 9, 11 |
| Minor (Aeolian) | 0, 2, 3, 5, 7, 8, 10 |
| Dorian | 0, 2, 3, 5, 7, 9, 10 |
| Phrygian | 0, 1, 3, 5, 7, 8, 10 |
| Lydian | 0, 2, 4, 6, 7, 9, 11 |
| Mixolydian | 0, 2, 4, 5, 7, 9, 10 |
| Locrian | 0, 1, 3, 5, 6, 8, 10 |
| Pentatonic Major | 0, 2, 4, 7, 9 |
| Pentatonic Minor | 0, 3, 5, 7, 10 |
| Blues | 0, 3, 5, 6, 7, 10 |
| Chromatic | 0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11 |

### Transposer
```cpp
namespace oc::note::scale {
struct Transposer {
    /// Transpose note par demi-tons (chromatic)
    static uint8_t transposeSemitones(uint8_t note, int8_t semitones);

    /// Transpose par degrés de gamme (scale-aware)
    static uint8_t transposeDegrees(uint8_t note, int8_t degrees, const Scale& scale);
};
}
```

---

## Annexe : Système de Presets

### Presets de Base (v1)

Chaque Track FX inclut des presets de base :

| FX | Presets |
|----|---------|
| **Chord** | Octave, Power5, Major, Minor, Sus4, 7th |
| **Ratchet** | x2, x3, x4, Roll |
| **Humanize** | Subtle (5%), Medium (15%), Drunk (30%) |
| **Delay** | Short (1/16), Medium (1/8), Long (1/4), Dotted, Triplet |
| **Swing** | Light (10%), Medium (33%), Heavy (66%) |

### Presets Utilisateur (v2+)

- Save/Load presets custom par FX
- Export/Import presets
- Presets de chaîne complète (FXChain)

---

## Annexe : Fonctionnalités Additionnelles

### MIDI Learn

**Mode Record :**
1. Appui sur bouton Record
2. Chaque note MIDI reçue → affecte le step courant
3. Passe automatiquement au step suivant
4. Second appui Record → arrête l'enregistrement

**Mode Per-Step :**
1. En mode Pitch, long press sur un macro
2. Jouer une note sur clavier externe
3. La note est affectée au step sélectionné

### Voice Limiter

- **Setting global** dans SequencerSettings
- **Valeur par défaut** : 16 voix simultanées
- **Comportement** : Note stealing (oldest note first) quand limite atteinte
- **Raison** : Évite saturation MIDI avec multi-track + FX génératifs

### Undo/Redo (v2)

À définir - probablement Command Pattern avec historique limité.

### Copy/Paste (v2)

- Copy step → Paste step
- Copy range → Paste range
- Copy track → Paste track

---

## Annexe : Protocol FILE_* (Chunking Binaire)

### Principes

- **Chunking** : Fichiers découpés en chunks de ~200 bytes max
- **Format** : Messages Binary standard (COBS encoding)
- **Vitesse** : USB natif (~12 Mbps), transfert quasi-instantané
- **Reprise** : Offset permet de reprendre un transfert interrompu

### Messages

#### FileListRequest / FileListResponse
```cpp
// Request
struct FileListRequest {
    char path[64];  // Ex: "/sequences"
};

// Response (peut nécessiter plusieurs messages si beaucoup d'entrées)
struct FileListResponse {
    uint8_t totalEntries;
    uint8_t chunkIndex;
    uint8_t entriesInChunk;  // max ~6 par message
    struct Entry {
        char name[32];
        uint32_t size;
        uint8_t flags;  // bit 0 = isDir
    } entries[6];
};
```

#### FileReadRequest / FileReadResponse
```cpp
// Request
struct FileReadRequest {
    char path[64];
    uint32_t offset;      // byte offset dans le fichier
    uint16_t maxLength;   // bytes demandés (max ~200)
};

// Response
struct FileReadResponse {
    uint32_t totalSize;   // taille totale fichier
    uint32_t offset;      // offset de ce chunk
    uint16_t length;      // bytes dans ce chunk
    uint8_t data[200];    // contenu
    uint8_t flags;        // bit 0 = isLast
};
```

#### FileWriteRequest / FileWriteResponse
```cpp
// Request
struct FileWriteRequest {
    char path[64];
    uint32_t offset;      // 0 = début (crée/écrase)
    uint16_t length;
    uint8_t flags;        // bit 0 = isLast (commit)
    uint8_t data[180];
};

// Response
struct FileWriteResponse {
    uint8_t status;       // 0 = OK, autres = erreur
    uint32_t bytesWritten;
};
```

#### FileDeleteRequest / FileInfoRequest
```cpp
struct FileDeleteRequest {
    char path[64];
};

struct FileDeleteResponse {
    uint8_t status;  // 0 = OK
};

struct FileInfoRequest { };  // Pas de paramètres

struct FileInfoResponse {
    uint32_t totalBytes;
    uint32_t usedBytes;
    uint32_t freeBytes;
};
```

### Flow Exemple (Lecture 4KB)

```
oc-bridge                              Teensy
    │                                     │
    │ FileReadRequest(path, offset=0)     │
    ├────────────────────────────────────>│
    │                                     │
    │ FileReadResponse(200 bytes, more)   │
    │<────────────────────────────────────┤
    │                                     │
    │ FileReadRequest(offset=200)         │
    ├────────────────────────────────────>│
    │                                     │
    │ FileReadResponse(200 bytes, more)   │
    │<────────────────────────────────────┤
    │           ... (20 chunks)           │
    │                                     │
    │ FileReadResponse(last chunk)        │
    │<────────────────────────────────────┤
    │                                     │
    │ ──► Reconstitue fichier complet     │
```

### Intégration oc-bridge

```rust
// oc-bridge reconstruit le fichier pour l'API REST
async fn handle_file_read(path: &str) -> Result<Vec<u8>> {
    let mut buffer = Vec::new();
    let mut offset = 0u32;

    loop {
        let req = FileReadRequest { path, offset, maxLength: 200 };
        let resp = serial.send_and_receive(req).await?;

        buffer.extend_from_slice(&resp.data[..resp.length as usize]);

        if resp.flags & 0x01 != 0 {  // isLast
            break;
        }
        offset += resp.length as u32;
    }

    Ok(buffer)
}
```

---

## Annexe : FXChain et Scheduler

### FXChain Structure

```cpp
namespace oc::note::fx {

class FXChain {
public:
    static constexpr size_t MAX_FX = 8;

    void addFX(FXType type, const FXParams& params);
    void removeFX(size_t index);
    void reorderFX(size_t from, size_t to);
    void clear();

    size_t size() const { return count_; }
    INoteFX* at(size_t index);

    void process(const std::span<const NoteEvent>& input,
                 std::vector<NoteEvent>& output,
                 const FXContext& context);

private:
    std::array<std::unique_ptr<INoteFX>, MAX_FX> fx_;
    size_t count_ = 0;
    std::vector<NoteEvent> buffer_;  // Buffer intermédiaire réutilisé
};

}  // namespace oc::note::fx
```

### FX Factory

```cpp
namespace oc::note::fx {

// Params union pour éviter std::variant
struct FXParams {
    FXType type;
    union {
        struct { uint8_t divisions; float decay; } ratchet;
        struct { int8_t intervals[8]; uint8_t count; uint8_t mode; } chord;
        struct { uint8_t mode; } scaleQuantize;
        struct { float velocityVar; float timingVar; float gateVar; } humanize;
        struct { float amount; } swing;
        struct { uint32_t delayTicks; uint8_t repeats; float velocityDecay; float gateDecay; } delay;
        struct { int8_t semitones; } transpose;
    };
};

std::unique_ptr<INoteFX> createFX(const FXParams& params);

}  // namespace oc::note::fx
```

### Scheduler (Note Priority Queue)

```cpp
namespace oc::note::sequencer {

struct ScheduledNote {
    uint32_t tick;           // Tick absolu de déclenchement
    NoteEvent event;
    bool isNoteOff;          // true = NoteOff, false = NoteOn

    bool operator>(const ScheduledNote& other) const {
        return tick > other.tick;  // Min-heap
    }
};

class NoteScheduler {
public:
    void schedule(const ScheduledNote& note);
    void processUntil(uint32_t tick, ISequencerOutput& output);
    void clear();

private:
    std::priority_queue<ScheduledNote,
                        std::vector<ScheduledNote>,
                        std::greater<ScheduledNote>> queue_;
};

}  // namespace oc::note::sequencer
```

### SequencerEngine avec Lookahead

```cpp
namespace oc::note::sequencer {

class SequencerEngine {
public:
    static constexpr uint8_t LOOKAHEAD_STEPS = 2;

    SequencerEngine(SequencerState& state,
                    ISequencerOutput& output,
                    IClockSource& clock);

    // Appelé par la clock à chaque tick
    void onTick(uint32_t tick);

private:
    void scheduleUpcomingNotes(uint32_t currentTick);
    void applyFXChain(TrackState& track,
                      std::vector<NoteEvent>& notes,
                      const FXContext& context);

    SequencerState& state_;
    ISequencerOutput& output_;
    IClockSource& clock_;
    NoteScheduler scheduler_;
    uint32_t lastScheduledStep_ = 0;
};

}  // namespace oc::note::sequencer
```
