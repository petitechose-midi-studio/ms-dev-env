# Memories

Documentation persistante et mémoires de travail pour MIDI Studio (et OpenControl).

## Structure

```
memories/
├── global/              # Documentation cross-project
├── open-control/        # Framework & tools
├── midi-studio/         # Produit
├── setup-architecture/   # Setup + distribution architecture
├── work/                # Travaux en cours
└── _OLD/                # Archives
```

## Conventions

### Fichiers permanents (global/, open-control/, midi-studio/)

- `roadmap.md` - Vision et prochaines étapes
- `architecture.md` - Comment ça marche
- `changelog.md` - Historique des changements
- `overview.md` - Vue d'ensemble, paths
- `hardware.md` - Spécifique hardware (midi-studio)

### Mémoires de travail (work/)

**Nommage**: `<type>-<scope>-<name>.md`

| Élément | Valeurs |
|---------|---------|
| type | `feature`, `refactor`, `fix`, `doc`, `chore` |
| scope | `oc` (open-control), `ms` (midi-studio), `all` (cross-project) |
| name | kebab-case descriptif |

**Exemples**:
- `feature-ms-sdl-storage.md`
- `refactor-oc-hal-naming.md`
- `fix-all-build-warnings.md`

**Header standard**:
```markdown
# <Type>: <Titre>

**Scope**: <projets concernés>
**Status**: planned | started | blocked | review | done
**Created**: YYYY-MM-DD
**Updated**: YYYY-MM-DD

## Objectif
...
```

**Multi-phase (> 2 semaines)** → Dossier:
```
work/feature-ms-sequencer/
├── README.md          # Overview + état global
├── phase-1-ui.md
└── phase-2-midi.md
```

### Archivage (_OLD/)

Quand terminé, déplacer vers `_OLD/` avec préfixe date:
```
_OLD/2026-01-17-refactor-oc-naming.md
```

## Index des fichiers

### global/
| Fichier | Description |
|---------|-------------|
| `commands.md` | Commandes utiles du projet |
| `code-style.md` | Conventions de code |

### open-control/
| Fichier | Description |
|---------|-------------|
| `changelog.md` | Historique des changements framework |

### midi-studio/
| Fichier | Description |
|---------|-------------|
| `overview.md` | Vue d'ensemble, paths, architecture |
| `changelog.md` | Historique des changements produit |
| `hw-layout.md` | Hardware layout reference |
| `hw-mapping-template.md` | Template pour hardware mappings |
| `hw-navigation.md` | Navigation patterns |
| `hw-sequencer.md` | Sequencer overlay mappings |

### work/ (travaux en cours)
| Fichier | Status | Description |
|---------|--------|-------------|
| `feature-ms-preset-storage/` | in progress | Système de presets avec persistence (dossier multi-phase) |
| `feature-ms-sequencer/` | planned | Step Sequencer modulaire (dossier multi-phase) |
| `refactor-all-dev-cli-dx-max/` | completed | Refactor setup + ms CLI pour DX maximale |
| `feature-all-distribution-installer/` | planned | Nightly/release channels + manifest + installer end-user |
| `feature-teensy-uploader-cli/` | planned | Flasher CLI Rust (Teensy 4.1), base pour l'installer |
