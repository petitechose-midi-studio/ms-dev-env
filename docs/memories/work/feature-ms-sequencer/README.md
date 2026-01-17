# Feature: Step Sequencer Modulaire

**Status:** planned  
**Project:** midi-studio (core + plugin-bitwig)  
**Created:** 2026-01-07  
**Priority:** high  

## Objectif

Séquenceur à pas multi-track (16 pistes) avec:
- 7 Step Properties: Note, Velocity, Gate, Probability, TimeOffset, Slide, Accent
- Track FX Chain: Ratchet, Chord, Scale Quantize, Humanize, Swing, etc.
- Mode exclusif vs Mode Macro (switch via LEFT_TOP)
- Storage LittleFS 6MB (JSON)

## Architecture

```
open-control/note/           # Nouvelle lib: moteur séquenceur
open-control/ui-lvgl-components/  # Widget LVGL séquenceur
midi-studio/core/            # Intégration standalone
midi-studio/plugin-bitwig/   # Intégration Bitwig
```

## Phases

| Phase | Description | Status |
|-------|-------------|--------|
| 1 | Architecture & interfaces | planned |
| 2 | Moteur séquenceur (engine) | planned |
| 3 | Track FX Chain | planned |
| 4 | UI LVGL | planned |
| 5 | Storage & persistence | planned |
| 6 | Intégration Core standalone | planned |
| 7 | Intégration Plugin Bitwig | planned |

## Fichiers

- `tech-spec.md` - Spécification technique complète (1500+ lignes)

## Voir aussi

- `midi-studio/hw-layout.md` - Hardware IDs
- `midi-studio/hw-navigation.md` - Patterns de navigation
- `midi-studio/hw-sequencer.md` - Mappings séquenceur (overlay)
