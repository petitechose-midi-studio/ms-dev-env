---
title: 'Step Sequencer Modulaire'
slug: 'step-sequencer-modular'
created: '2026-01-07'
updated: '2026-01-29'
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

This is the long-term, modular direction for the sequencer engine.

- v0 (UI-first / produit minimal): `docs/memories/work/feature-ms-sequencer/tech-spec.md`
- v0->framework execution plan: `docs/memories/work/feature-ms-sequencer/implementation-plan-v0-framework.md`

# Tech-Spec: Step Sequencer Modulaire

**Created:** 2026-01-07

**Status (2026-01-29):** planned. No implementation work is scheduled until the end-user distribution (stable/beta + ms-manager/ms-updater) is solid.

## Overview

### Problem Statement

MIDI Studio a besoin d'un sequenceur a pas programmable fonctionnant en standalone avec une architecture reutilisable pour le contexte Bitwig. Le sequenceur doit etre multi-track (16 pistes), avec une separation claire entre les **Step Properties** (donnees par pas) et les **Track FX** (transformations globales), et proposer une experience coherente entre les deux contextes d'execution.

### Solution

Creer un nouveau repo `open-control/note/` contenant la logique pure du sequenceur (moteur, Track FX, scales, clock) avec des interfaces abstraites pour l'output et la synchronisation. L'UI LVGL sera dans `open-control/ui-lvgl-components/`. MIDI Studio Core et Plugin Bitwig consommeront cette bibliotheque avec leurs propres implementations des interfaces.

**Architecture cle :** Le step sequenceur genere des notes avec leurs proprietes (note, velocity, gate, probability, timing, slide, accent), puis les Track FX transforment ce flux (ratchet, chord, humanize, swing, etc.).

### Scope

**In Scope:**
- Moteur sequenceur multi-track (16 tracks max)
- **7 Step Properties** : Note, Velocity, Gate, Probability, TimeOffset (plus/minus 50%), Slide, Accent
- **Track FX Chain** : Ratchet, Chord, Scale Quantize, Humanize, Swing, Delay, Transpose
- Micro-timing per-step (plus/minus 0.5 step)
- Gate > 100% (notes longues debordant sur steps suivants)
- Widget LVGL themable (8 steps visibles, pagination)
- Overlays : Global (Track FX, selection propriete) + Per-Step (override proprietes)
- Integration Core standalone (USB MIDI, clock interne/externe)
- Integration Plugin Bitwig (Protocol Serial, clock Bitwig, scale Bitwig)
- Mute/Solo par track
- Resolution 24 PPQN
- Voice limiter global (settings)
- MIDI Learn (mode record + per-step)
- **Storage** : SD card (Teensy, SDIO) + file (desktop). Format TBD (JSON draft).
- **GUI Manager PC** : Web GUI (localhost:9001) - in scope v1 mais pas prioritaire
- **Protocol FILE_*** : Commandes transfert fichiers via oc-bridge (chunking Binary)

**Out of Scope (v2+):**
- Modes arpeggiator additionnels (v1 = Up/Down dans Chord FX)
- Presets utilisateur custom (save/load) - Note: presets de BASE inclus en v1
- Modulation Bitwig -> Controller
- Step recording depuis Bitwig
- Pattern presets (save/load sequences completes)
- Undo/Redo complet (v1 = basique ou absent)
- Copy/Paste avance (v1 = basique)

## Mode Exclusif

Le sequenceur est un **mode exclusif** par rapport au mode Macro :
- **Mode Macro** : Comportement actuel (8 encodeurs = 8 macros CC)
- **Mode Sequencer** : Les 8 encodeurs controlent les 8 steps visibles

Un seul mode actif a la fois. Switch via **LEFT_TOP** -> Mode Selector (voir `docs/memories/midi-studio/hw-navigation.md`).

## Interactions Hardware

> **Reference :** Voir `docs/memories/midi-studio/hw-navigation.md` pour les patterns universels MIDI Studio.
> **Reference :** Voir `docs/memories/midi-studio/hw-layout.md` pour le schema physique et IDs.

### Mapping Mode Sequencer (Vue Principale)

| Controle | Press | Long Press | Turn |
|----------|-------|------------|------|
| **LEFT_TOP** | Mode Selector | Breadcrumb | - |
| **LEFT_CENTER** | Pattern Config | Track Config | - |
| **LEFT_BOTTOM** | Property Selector | - | - |
| **NAV** | Sequencer Settings | - | Select track (1-16) |
| **OPT** | - | - | Fine tune last touched |
| **MACRO 1-8** | Toggle step | Step Edit + MIDI Learn | Adjust property |
| **BOTTOM_LEFT** | Page <- | Copy step | - |
| **BOTTOM_CENTER** | Play/Pause | Stop | - |
| **BOTTOM_RIGHT** | Page -> | Paste step | - |

> **Reference complete :** Voir `docs/memories/midi-studio/hw-sequencer.md` pour les overlays.

### Structure Overlays Sequenceur

```
MODE SEQUENCER (Vue principale)
|
|--- LEFT_TOP press ----> MODE SELECTOR
|
|--- LEFT_CENTER press -> PATTERN CONFIG (Length, Save/Load/Delete)
|--- LEFT_CENTER long --> TRACK CONFIG (10 items, 2 pages)
|                        |--- Scale Selector (3 params)
|                        \--- FX Chain
|                             |--- Add FX
|                             \--- FX Config
|
|--- LEFT_BOTTOM press -> PROPERTY SELECTOR (7 props)
|
|--- NAV press --------> SEQUENCER SETTINGS
|                        \--- Data Manager
|                             \--- File Picker
|
\--- MACRO long -------> STEP EDIT (8 params)
```

## Overlays Sequenceur

### Overlay Global (bouton gauche)

Permet de configurer la track active au niveau global :

| Fonction | Description |
|----------|-------------|
| **Selection propriete** | Choisir quelle propriete les encodeurs modifient (note, velocity, gate, probability, timing) |
| **Track FX Chain** | Voir/modifier la chaine d'effets de la track |
| **Ajout FX** | Ajouter un effet a la chaine |
| **Config FX** | Parametrer un effet (presets, valeurs custom) |
| **Retrait FX** | Retirer un effet de la chaine |
| **Selection scale** | Choisir la gamme active pour la track |

Navigation : **Nav encoder** pour se deplacer, **Optical encoder** pour ajuster les valeurs.

### Overlay Per-Step (long press macro)

Permet de configurer un step specifique (proprietes uniquement, pas de FX) :

| Fonction | Description |
|----------|-------------|
| **Note** | Definir la note MIDI (0-127) |
| **Velocity** | Definir la velocite (0-127) |
| **Gate** | Definir la duree (0% - 300%+) |
| **Probability** | Definir la probabilite (0-100%) |
| **Time Offset** | Micro-timing (-50% a +50% du step) |
| **Slide** | Activer/desactiver le legato |
| **Accent** | Activer/desactiver l'accent |
| **Clear overrides** | Remettre le step aux valeurs par defaut |

Navigation : **Nav encoder** pour se deplacer, **Optical encoder** pour ajuster les valeurs.

## Systeme Timing / Mesure

### Calcul Duree Step

```
Duree Step = Longueur Mesure / Nombre de Steps

Exemple : Mesure = 4 temps (1 bar), Steps = 8
-> Duree Step = 4/8 = 0.5 temps = 1 croche
```

### Configuration

| Parametre | Valeur | Scope |
|-----------|--------|-------|
| **Longueur mesure** | Ex: 4 temps (1 bar) | Global sequenceur |
| **Nombre de steps** | Configurable (8, 16, 32...) | Par track |
| **Steps visibles** | 8 par defaut (= 8 encodeurs) | Configurable |
| **Resolution** | 24 PPQN | Global |

### Gate > 100%

Une note peut deborder sur les steps suivants :
- Gate 100% = note dure exactement 1 step
- Gate 150% = note dure 1.5 steps
- Gate 300% = note dure 3 steps
- NoteOff calcule en **absolu** (pas relatif au step)

### Micro-timing (Time Offset)

Chaque step peut etre decale par rapport a la grille :

| Valeur | Signification |
|--------|---------------|
| `-0.5` | Demi-step en avance |
| `0.0` | Sur la grille (defaut) |
| `+0.5` | Demi-step en retard |

- **Range** : plus/minus 50% du step (plus/minus 0.5)
- **Unite** : Fraction de step
- **UX** : Encodeur en mode "Timing" ajuste cette valeur

```cpp
uint32_t calculateTriggerTick(uint8_t stepIndex, float timeOffset, uint32_t ticksPerStep) {
    int32_t baseTick = stepIndex * ticksPerStep;
    int32_t offsetTicks = static_cast<int32_t>(timeOffset * ticksPerStep);
    return std::max(0, baseTick + offsetTicks);
}
```

## Architecture Memoire & Storage

### Zones Memoire Teensy 4.1

| Zone | Taille | Usage |
|------|--------|-------|
| **RAM1 (DTCM)** | 512 KB | Code temps-reel, stack, variables critiques |
| **RAM2 (OCRAM)** | 512 KB | Framebuffer LVGL, DMA buffers |
| **PSRAM** | 8 MB | SequencerState runtime, Undo history |
| **SD card (SDIO)** | (varies) | Persistence : sequences, presets, settings |

### Repartition Sequenceur

```cpp
// PSRAM : Donnees runtime (volatile)
EXTMEM SequencerState sequencerState;        // ~20 KB
EXTMEM UndoHistory undoHistory;               // ~500 KB

// RAM1 : Temps-reel critique
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

### Flow Memoire

```
Boot -> SD card -> PSRAM (load)
Edit -> PSRAM (runtime)
Save -> PSRAM -> SD card (persist)
Tick -> PSRAM -> RAM1 (prepareNextTick) -> Output
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

### Presets de Base (generes en code)

Au premier boot, le firmware genere les presets de base :

```cpp
void createDefaultPresets() {
    // FX Presets
    writeJsonIfNotExists("/midi-studio/presets/fx/ratchet_x2.json",
        R"({\"type\":\"ratchet\",\"divisions\":2,\"decay\":0})");
    writeJsonIfNotExists("/midi-studio/presets/fx/ratchet_x4.json",
        R"({\"type\":\"ratchet\",\"divisions\":4,\"decay\":0.2})");
    writeJsonIfNotExists("/midi-studio/presets/fx/swing_medium.json",
        R"({\"type\":\"swing\",\"amount\":0.33})");
    writeJsonIfNotExists("/midi-studio/presets/fx/humanize_subtle.json",
        R"({\"type\":\"humanize\",\"velocity\":0.05,\"timing\":0.03})");
    // ... autres presets
}

void createDefaultSettings() {
    writeJsonIfNotExists("/midi-studio/settings/global.json",
        R"({\"voiceLimit\":16,\"defaultBpm\":120})");
}
```

### Structure Fichiers

```
/midi-studio/
|-- sequences/
|   |-- pattern_01.json
|   |-- pattern_02.json
|   \-- ...
|-- presets/
|   |-- fx/
|   |   |-- ratchet_x2.json      (genere au 1er boot)
|   |   |-- ratchet_x4.json      (genere au 1er boot)
|   |   |-- swing_medium.json    (genere au 1er boot)
|   |   \-- user_custom.json     (cree par utilisateur)
|   \-- chains/
|       \-- techno_lead.json
|-- settings/
|   \-- global.json              (genere au 1er boot)
\-- backup/
    \-- autosave.json
```

### Format JSON (exemple sequence)

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

**Note :** Le pattern est maintenant un objet imbrique dans la track, contenant uniquement les donnees (name, length, steps). Les parametres de playback (resolution, division, direction, offset) sont au niveau track.

### Comportement Contextes

- **Standalone** : Etat charge depuis SD card au boot -> PSRAM
- **Bitwig** : Meme etat, Bitwig y accede via Protocol
- **Arret Bitwig** : Sequenceur continue avec son etat PSRAM
- **Save** : PSRAM -> SD card (auto-save ou manuel)

## GUI Manager (PC)

### Architecture

```
|---------------------------------------------------------|
|           MIDI Studio Manager (Web GUI)                 |
|              http://localhost:9001                      |
|---------------------------------------------------------|
|  - Liste fichiers (tree view)                           |
|  - Preview JSON (BPM, tracks, steps)                    |
|  - Selection multiple                                   |
|  - Download vers PC                                     |
|  - Upload depuis PC (drag & drop)                       |
|  - Suppression                                          |
|  - Espace disque utilise/libre                          |
|---------------------------------------------------------|
                         |
                         v HTTP REST API
|---------------------------------------------------------|
|                     oc-bridge                           |
|         UDP:9000 (Bitwig) + HTTP:9001 (GUI)             |
|---------------------------------------------------------|
                         |
                         v Binary Protocol
                    [ Teensy 4.1 ]
```

### Protocol : Commandes FILE_*

| Commande | Description |
|----------|-------------|
| `FILE_LIST <path>` | Liste les fichiers d'un repertoire |
| `FILE_READ <path>` | Lit le contenu d'un fichier (JSON) |
| `FILE_WRITE <path> <data>` | Ecrit un fichier |
| `FILE_DELETE <path>` | Supprime un fichier |
| `FILE_INFO` | Retourne espace total/utilise/libre |

### REST API (oc-bridge HTTP:9001)

| Endpoint | Methode | Description |
|----------|---------|-------------|
| `/api/files?path=/sequences` | GET | Liste fichiers |
| `/api/files/sequences/pattern_01.json` | GET | Lit fichier |
| `/api/files/sequences/pattern_01.json` | PUT | Ecrit fichier |
| `/api/files/sequences/pattern_01.json` | DELETE | Supprime |
| `/api/storage` | GET | Info espace disque |

### Technologies GUI

- **Frontend** : Web (React ou Svelte) servi par oc-bridge
- **Acces** : Navigateur sur `http://localhost:9001`
- **Pas d'installation** : oc-bridge sert les fichiers statiques

## Context for Development

### Codebase Patterns

**Patterns existants a suivre :**
- `Signal<T>` pour etat reactif (subscriptions RAII)
- `DerivedSignal` pour valeurs calculees
- `SignalWatcher` pour coalescing multi-signal
- Props pattern pour overlays stateless
- Fluent input bindings : `onButton(X).press().scope(S).then(fn)`
- Three-layer separation : Handlers -> State -> Views
- Interfaces abstraites pour decouplage (IClockSource, ISequencerOutput)

**Nouveaux patterns introduits :**
- `INoteFX` pipeline avec `process(input, output, context)`
- `FXChain` configurable et ordonnee (par track)
- `NoteEvent` comme unite de traitement dans le pipeline FX
- **Separation Step Properties / Track FX** : les steps contiennent les donnees, les FX transforment le flux
- `NoteScheduler` avec lookahead pour timing precis (humanize bipolaire, delay)

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
**Note :** `sendNoteOff` inclut velocity pour compatibilite avec `IMidiTransport` existant. Defaut = 0 (ou valeur NoteOn si pertinent).

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
**Usage :** Bitwig implemente `IScaleProvider` pour fournir la scale du projet au sequenceur Core.

#### INoteFX (Track FX Pipeline)
```cpp
namespace oc::note::fx {

struct NoteEvent {
    uint8_t note;
    uint8_t velocity;
    uint8_t channel;
    float gate;              // 0.0+ (peut depasser 1.0)
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

**Note :** Les Track FX ne connaissent pas les steps individuels. Ils transforment un flux de `NoteEvent` genere par le sequenceur.

### Files to Reference

| File | Purpose |
| ---- | ------- |
| `open-control/framework/src/oc/state/Signal.hpp` | Pattern Signal pour etat reactif |
| `open-control/framework/src/oc/core/input/ButtonBuilder.hpp` | Fluent API pour bindings |
| `midi-studio/core/src/state/CoreState.hpp` | Structure etat existante |
| `midi-studio/core/src/ui/macro/MacroEditOverlay.hpp` | Pattern overlay existant |
| `midi-studio/core/docs/HOW_TO_ADD_HANDLER.md` | Guide creation handler |
| `midi-studio/core/docs/HOW_TO_ADD_OVERLAY.md` | Guide creation overlay |
| `open-control/hal-teensy/src/oc/teensy/UsbMidi.hpp` | Interface USB MIDI existante |
| `midi-studio/plugin-bitwig/src/handler/input/ViewSwitcherInputHandler.cpp` | Pattern switch mode avec overlay |
| `midi-studio/plugin-bitwig/src/state/ViewManager.hpp` | Pattern ViewManager multi-vues |

### Memory References

| Doc | Purpose |
| --- | ------- |
| `docs/memories/midi-studio/hw-layout.md` | Schema physique controleur, IDs boutons/encodeurs |
| `docs/memories/midi-studio/hw-mapping-template.md` | Template pour definir mappings par ecran/overlay |
| `docs/memories/midi-studio/hw-navigation.md` | Patterns navigation universels |
| `docs/memories/midi-studio/hw-sequencer.md` | Mappings sequenceur |

### Technical Decisions

**1. Localisation du code sequenceur**
- Decision : Nouveau repo `open-control/note/` (pas dans midi-studio)
- Raison : Reutilisable par tout projet OpenControl, agnostique hardware

**2. Namespaces**
- `oc::note::sequencer` - Moteur, TrackState, StepState
- `oc::note::fx` - INoteFX, FXChain, tous les Track FX
- `oc::note::scale` - Scale, ScaleRegistry, Transposer
- `oc::note::clock` - IClockSource, implementations

**3. Resolution horloge**
- Decision : 24 PPQN
- Raison : Standard MIDI Clock, compatible hardware externe

**4. Architecture Step Properties + Track FX**
- Decision : Separation claire entre donnees (Step) et transformations (FX)
- Raison : Clarite conceptuelle, proche de l'etat de l'art

**5. Multi-track**
- Decision : 16 tracks max, canal MIDI par defaut = index track

**6. Gate > 100%**
- Decision : Supporte, NoteOff calcule en absolu

**7. Contexte Bitwig**
- Decision : Bitwig accede au sequenceur Core via Protocol, pas de duplication

**8. Voice Limiter**
- Decision : Limiter global dans les settings, pas per-track
- Valeur par defaut : 16 voix simultanees

**9. MIDI Learn**
- Decision : Mode record + per-step

**10. Organisation Repo**
- Decision : `open-control/note/` est un repo git separe (pas un submodule)

**11. SequencerState et CoreState**
- Decision : DI - SequencerState separe de CoreState (memoire)

**12. FXChain Ordre**
- Decision : Configurable par l'utilisateur

**13. Clock Source Priorite**
- Decision : Auto-detection avec override dans settings
- Priorite par defaut : MIDI Clock externe > Bitwig (si connecte) > Interne

**14. Voice Limiter Algorithme**
- Decision : Oldest first, global

**15. Accent Comportement**
- Decision : Configurable, defaut +50% velocity

**16. Slide (Legato) Implementation**
- Decision : Overlap (NoteOn avant NoteOff precedent)

**17. Clock Architecture**
- Decision : Push + Scheduler avec lookahead

**18. Swing Comportement**
- Decision : Timing only sur off-beats

**19. HumanizeFX**
- Decision : Bipolaire (plus/minus timing)

**20. DelayFX Parametres**
- delayTicks, repeats, velocityDecay, gateDecay

**21. Scale Source**
- Decision : Track.scale est la reference unique

**22. Playhead Multi-track**
- Decision : Modulo - `globalStep % track.length`

**23. Signal<T>**
- Decision : Obligatoire

**24. Auto-save**
- Decision : Event + timeout (AutoPersist)

**25. Hierarchie Donnees**
- Projet / Sequence / Pattern

**26. FXType Enum**
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

**27. Bitwig Acces**
- Decision : Acces direct au SequencerState depuis contexte Bitwig

**28. MIDI Channel Convention**
- Interne : 0-based (0-15)
- Affichage : 1-based (1-16)

**29. Separation Pattern / Track**
- Decision : Pattern = donnees pures, Track = config playback

**30. Architecture BPM Deux Niveaux**
- Decision : Default BPM (settings) + Session BPM (runtime)

## Implementation Plan

### Phase 1 : Architecture Core (open-control/note/)

**A definir dans Step 2 : Investigation approfondie**
- Structure detaillee des fichiers
- Interfaces completes
- Tests unitaires

### Phase 2 : UI (open-control/ui-lvgl-components/)

**A definir dans Step 2**
- StepSequencerWidget
- StepWidget
- Theme system

### Phase 3 : Integration MIDI Studio

**A definir apres Phase Layout**
- Handlers navigation
- Overlays
- Bindings hardware

### Tasks

**A completer dans Step 2 (Investigation)**

### Acceptance Criteria

**A completer dans Step 3 (Generate)**

## Additional Context

### Dependencies

**open-control/note/ depend de :**
- C++ STL uniquement (pour portabilite)
- Optionnel : `oc::state::Signal<T>` du framework (pour reactivite)

**NE depend PAS de :**
- CoreState
- LVGL
- HAL specifique

**midi-studio/core/ depend de :**
- `open-control/note/`
- `open-control/ui-lvgl-components/`
- `open-control/hal-teensy/`

### Testing Strategy

**Unit Tests (open-control/note/) :**
- Chaque Track FX individuellement
- FXChain
- Scale
- SequencerEngine tick processing
- NoteEvent generation

**Integration Tests (midi-studio/core/) :**
- Overlay lifecycle
- Handler bindings
- Multi-track playback
- Clock sync
- Voice limiter
- MIDI Learn

---

## Annexe : Structure Fichiers Repos

### open-control/note/
```
open-control/note/
|-- library.json
|-- README.md
\-- src/oc/note/
    |-- sequencer/
    |   |-- SequencerEngine.hpp
    |   |-- SequencerState.hpp
    |   |-- SequencerSettings.hpp
    |   |-- PlaybackTypes.hpp
    |   |-- StepState.hpp
    |   |-- PatternState.hpp
    |   |-- TrackState.hpp
    |   |-- NoteEvent.hpp
    |   |-- NoteScheduler.hpp
    |   \-- ISequencerOutput.hpp
    |-- fx/
    |   |-- INoteFX.hpp
    |   |-- FXChain.hpp
    |   |-- FXContext.hpp
    |   |-- RatchetFX.hpp
    |   |-- ChordFX.hpp
    |   |-- ScaleQuantizeFX.hpp
    |   |-- HumanizeFX.hpp
    |   |-- SwingFX.hpp
    |   |-- DelayFX.hpp
    |   \-- TransposeFX.hpp
    |-- scale/
    |   |-- Scale.hpp
    |   |-- ScaleRegistry.hpp
    |   |-- Transposer.hpp
    |   \-- IScaleProvider.hpp
    \-- clock/
        |-- IClockSource.hpp
        |-- InternalClock.hpp
        \-- MidiClockReceiver.hpp
```

### open-control/ui-lvgl-components/ (extension)
```
open-control/ui-lvgl-components/
\-- src/oc/ui/lvgl/sequencer/
    |-- StepSequencerWidget.hpp
    |-- StepWidget.hpp
    |-- StepSequencerTheme.hpp
    \-- IStepSequencerCallbacks.hpp
```

### midi-studio/core/ (integration)
```
midi-studio/core/src/
|-- sequencer/
|   |-- CoreSequencerIntegration.hpp
|   |-- UsbMidiOutput.hpp
|   |-- InternalClockSource.hpp
|   \-- ExternalMidiClockSource.hpp
|-- handler/sequencer/
|   |-- SequencerModeHandler.hpp
|   |-- SequencerStepHandler.hpp
|   |-- SequencerGlobalHandler.hpp
|   |-- SequencerStepOverlayHandler.hpp
|   \-- SequencerTrackHandler.hpp
\-- ui/sequencer/
    |-- SequencerView.hpp
    |-- SequencerGlobalOverlay.hpp
    \-- SequencerStepOverlay.hpp
```

### midi-studio/plugin-bitwig/ (integration)
```
midi-studio/plugin-bitwig/src/sequencer/
|-- BitwigClockSource.hpp
|-- ProtocolSequencerOutput.hpp
\-- BitwigScaleProvider.hpp
```
