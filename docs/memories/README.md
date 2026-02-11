# Memories

Documentation persistante et memoires de travail pour MIDI Studio (et OpenControl).

Point d'entree: `docs/memories/global/onboarding.md`

## Structure

```
memories/
├── global/              # Documentation cross-project
├── open-control/        # Framework & tools
├── midi-studio/         # Produit
├── setup-architecture/   # Setup + distribution architecture
└── work/                # Travaux en cours
```

## Archivage (hors repo)

Pour garder ce repo leger et eviter de versionner des plans historiques, les documents devenus obsoletes / termines sont archives **en dehors du repo**.

Emplacement recommande (local): `~/Desktop/legacy memories/ms-dev-env/`

Note: le contenu qui etait dans `docs/memories/_OLD/` et certains plans termines de `docs/memories/work/` ont ete archives dans ce dossier (2026-02-11).

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

### Archivage (hors repo)

Quand termine, deplacer vers le dossier Desktop, avec prefixe date si besoin.
Exemple:
```text
~/Desktop/legacy memories/ms-dev-env/docs/memories/2026-01-17-refactor-oc-naming.md
```

## Index des fichiers

### global/
| Fichier | Description |
|---------|-------------|
| `onboarding.md` | Point d'entree (start here) |
| `commands.md` | Commandes utiles du projet |
| `code-style.md` | Conventions de code |

### open-control/
| Fichier | Description |
|---------|-------------|
| `changelog.md` | Historique des changements framework |
| `README.md` | Vue d'ensemble (repos + pointers) |

### midi-studio/
| Fichier | Description |
|---------|-------------|
| `overview.md` | Vue d'ensemble, paths, architecture |
| `changelog.md` | Historique des changements produit |
| `hw-layout.md` | Hardware layout reference |
| `hw-mapping-template.md` | Template pour hardware mappings |
| `hw-navigation.md` | Navigation patterns |
| `hw-sequencer.md` | Sequencer overlay mappings |
| `shared-ui-ms-ui.md` | UI partagee (`ms-ui`) |

### work/ (travaux en cours)
| Fichier | Status | Description |
|---------|--------|-------------|
| `README.md` | active | Index des memoires de travail actives |
| `feature-ms-sequencer/` | started | Step sequencer (UI-first) |
| `ideas/` | active | Backlog d'idees |
