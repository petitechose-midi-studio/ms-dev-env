---
title: 'Step Sequencer v0 -> Framework Extraction Plan'
slug: 'step-sequencer-v0-framework-plan'
created: '2026-02-12'
updated: '2026-02-12'
status: 'active'
---

# Plan: v0 Produit + Structure Framework (oc-note)

## Progress log

- 2026-02-12:
  - Phase 0 docs + repo manifest update: `petitechose-midi-studio/ms-dev-env` PR #74.
  - Phase 1 oc-note skeleton pushed: `open-control/note` @ `e6b8645`.
  - Tests: `pio test -e native` in `open-control/note`.
  - Phase 2 oc-note v0 engine + clock pushed: `open-control/note` @ `73ab913`.
  - Tests: `pio test -e native` (clock + engine + smoke).

## Contexte

- Aujourd'hui, `midi-studio/core` a une UI sequencer fonctionnelle (8 steps visibles, pagination, focus, playhead state) et des handlers d'edition UI-first.
- La direction aboutie de la feature est une architecture modulaire (multi-track, FX chain, scheduler/lookahead, PPQN, clock interne/externe/Bitwig) a externaliser cote OpenControl.
- Objectif: livrer un v0 "produit" rapidement, sans se condamner a refaire le travail lors de l'extraction engine/clock/output.

## Objectifs v0 (produit)

- Playback mono-track (v0): 1 pattern, max 64 steps, longueur fixe initiale = 18 steps.
- Resolution: 1/16 par defaut (settings plus tard).
- Routage MIDI: canal 1 par defaut.
- Gate:
  - gate == 0 => pas de note (mute)
  - gate > 0 => NoteOff a (gate%) de la duree d'un step
- Velocity: 0 est une valeur valide, envoyee telle quelle.
- Playhead:
  - start playback => step 0
  - stop => playhead "none" + all notes off
- Important: le MIDI du sequencer doit partir tant que le transport est en lecture, peu importe la vue active (Macro/Sequencer/overlays).

## Contraintes et invariants

- State est la source de verite (UI = projection), cf. `midi-studio/core/docs/INVARIANTS.md`.
- L'engine ne doit jamais appeler `lv_*`.
- Le playback ne doit pas etre scope a une vue (pas de couplage d'autorite input).

## Design cible (v0 compatible v1+)

### Separation des responsabilites

- `oc-note` (nouvelle lib OpenControl): logique pure sequencer/clock/scheduler + interfaces abstraites.
- `midi-studio/core`: integration (adapters) + UI + mapping hardware.

### Separation state "engine" vs state "UI"

- State engine (reutilisable): longueur, playhead, params playback (channel, stepsPerBeat), mask enabled, donnees steps (note/velocity/gate/nudge).
- State UI-only (core): page visible, focusedStep, overlays.

### Interfaces (des maintenant)

- `ISequencerOutput`: abstraction sortie (USB MIDI en standalone, protocol/Bitwig plus tard).
- `IClockSource` / clock internal: abstraction du temps/tick domain.
- Tick domain standardise: PPQN = 24 (compatible MIDI clock), meme si v0 tourne en clock interne.

## Phase 0 - Docs (clarifier v0 vs direction)

- Ajouter la spec "modular" (v1+) dans le repo: `docs/memories/work/feature-ms-sequencer/tech-spec-modular.md` (status planned).
- Garder la spec v0 UI-first: `docs/memories/work/feature-ms-sequencer/tech-spec.md`.
- Lier les deux specs depuis `docs/memories/work/feature-ms-sequencer/README.md`.
- Mettre a jour `docs/memories/midi-studio/hw-sequencer.md` pour pointer vers v0 + modular.

## Phase 1 - Creer la lib `open-control/note` (oc-note)

### Objectifs

- Une lib PlatformIO comme les autres (`oc-framework`, `oc-hal-teensy`, etc.).
- Aucune dependance LVGL / HAL.
- Dependances autorisees:
  - C++17 STL (raisonnable)
  - `oc-framework` pour `Signal<T>` et types de callbacks (time provider)

### Fichiers

- `open-control/note/library.json`
- `open-control/note/platformio.ini` (tests native Unity, calque sur `open-control/framework/platformio.ini`)
- `open-control/note/src/oc/note/clock/*`
- `open-control/note/src/oc/note/sequencer/*`
- `open-control/note/test/*` (unit tests v0)

### Definition "Done" (Phase 1)

- `pio test -e native` dans `open-control/note` tourne.
- La lib compile en dependance (sans LVGL) dans un firmware Teensy.

## Phase 2 - Engine v0 dans `oc-note`

### State (engine)

Creer `oc::note::sequencer::StepSequencerState`:

- Constants explicites (pas de magic numbers):
  - `DEFAULT_PPQN = 24`
  - `DEFAULT_STEPS_PER_BEAT = 4` (=> 1/16)
  - `DEFAULT_MIDI_CHANNEL_0BASED = 0` (channel 1)
  - `DEFAULT_LENGTH = 18`
- Signals:
  - `length`
  - `playheadStep` (-1 = none)
  - `stepsPerBeat`
  - `midiChannel` (0..15)
- Donnees steps (non-signals, v0):
  - `enabledMask` (uint64)
  - `note[64]`, `velocity[64]`, `gate[64]` (0..100), `nudge[64]` (-50..50)

### Clock interne (PPQN)

Creer une clock interne qui convertit temps -> ticks:

- PPQN fixe = 24.
- `bpm` vient du contexte (v0: statusBar.tempo).
- Gestion du drift: accumulation (fixed point) pour generer des ticks stables meme si la periode n'est pas un multiple de 1ms.

### Scheduler minimal (v0)

- But: pouvoir planifier des NoteOff a un tick absolu (gate%).
- Structure simple sans allocation (table fixe / min-heap simple).
- Doit pouvoir:
  - schedule NoteOff
  - process events "due" avant NoteOn du step
  - clear sur stop

### Engine v0

- Start (front montant playing):
  - `playheadStep = 0`
  - trigger step 0 immediatement
- Avancement:
  - `ticksPerStep = PPQN / stepsPerBeat` (pour 1/16: 24/4=6)
  - `stepIndex = (tick / ticksPerStep) % length`
  - update `playheadStep`
- Emission MIDI:
  - si step enabled ET gate > 0 => NoteOn
  - NoteOff schedule: `stepStartTick + gate% * ticksPerStep / 100`
  - velocity 0 envoyee telle quelle
- Stop (front descendant):
  - `playheadStep = -1`
  - `output.allNotesOff()`
  - clear scheduler

### Tests (Phase 2)

- gate=0 => aucun NoteOn
- velocity=0 => NoteOn velocity 0 envoye
- NoteOff respecte gate% (ticks)
- Start => step 0 immediat
- Stop => allNotesOff + playhead=-1

## Phase 3 - Integration `midi-studio/core`

### Dependances

- Ajouter `oc-note` comme lib_dep (symlink) dans:
  - `midi-studio/core/platformio.ini`
  - `midi-studio/plugin-bitwig/platformio.ini` (plus tard, pour reuse engine)

### Wiring global (pas lie a la vue)

- Creer un petit service playback dans `StandaloneContext`:
  - instancie engine + clock + adapter output
  - ticke dans `StandaloneContext::update()`
  - lit `core_state_.statusBar.playing/tempo`

### Output adapter (standalone)

- Adapter `ISequencerOutput` -> `oc::api::MidiAPI` (USB MIDI out).
- Sur stop / cleanup: `midi().allNotesOff()`.

### UI

- La view continue de se baser sur `playheadStep` pour le bleu.
- Pas d'auto-follow (contract).

### Definition "Done" (Phase 3)

- En lecture: notes sortent en 1/16 sur canal 1, gate% respecte, velocity 0 OK.
- Le playback fonctionne meme si on est en vue Macro ou qu'un overlay est visible.
- Builds:
  - `pio run -e dev` dans `midi-studio/core`
  - `pio run -e dev` dans `midi-studio/plugin-bitwig`

## Phase 4 - Sync MIDI / Bitwig (framework, timebox)

Objectif: rendre la clock pluggable sans casser v0.

1) Etendre `oc::interface::IMidi` (non-breaking)
- Ajouter callbacks optionnels:
  - MIDI Clock tick (0xF8)
  - Start (0xFA), Stop (0xFC), Continue (0xFB)

2) Implementer HAL
- `open-control/hal-teensy/.../UsbMidi.*`: forward realtime
- `open-control/hal-midi/.../LibreMidiTransport.*`: parser realtime

3) `oc-note` clock externe
- `MidiClockReceiver` (PPQN=24) qui implemente `IClockSource`.

4) Politique de selection clock (plus tard)
- Priorite par defaut: MIDI externe > Bitwig > interne.
- Override via settings (overlay).

## Definition of Done globale (v0)

- v0 playback stable + UI playhead.
- Architecture deja compatible extraction vers engine modulaire (v1+), sans rewrite de la couche clock/output.
