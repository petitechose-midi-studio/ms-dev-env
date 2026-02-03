# Setup & Distribution Architecture

Ce document décrit l'architecture d'installation pour :

1) le dev environment (`ms-dev-env`, bootstrap via `uv` + `ms`)
2) la distribution end-user (stable/beta/nightly + ms-manager + ms-updater)

## Principes

- Entrée canonique (dev) : `uv run ms ...`
- Un seul workflow "one click" : `uv run ms setup --yes`
- Exécution safe : pas de `shell=True`, uniquement argv, et install système via allowlist
- Parité : Windows / macOS / Linux (Ubuntu + Fedora)

## Dev environment (actuel)

### Objectif

`git clone` + `uv run ms setup --yes` doit produire un environnement capable de :

- build/run simulateurs natifs (core, bitwig)
- build/serve simulateurs WASM (core, bitwig)
- build/upload/monitor firmware Teensy (core, bitwig)
- exécuter `oc-bridge` (précompilé par défaut)

### Commandes

- Setup complet : `uv run ms setup --yes`
- Vérifier : `uv run ms check`
- Synchroniser : `uv run ms sync --repos` / `uv run ms sync --tools`
- Status multi-repos : `uv run ms status`

### Layout workspace

```
ms-dev-env/
  ms/                  # CLI Python (package)
  open-control/         # repos OpenControl (git clones)
  midi-studio/          # repos MIDI Studio (git clones)
  tools/                # toolchains bundlées (dev)
  bin/                  # binaires buildés/installés (dev)
  .ms/                  # état/cache (PlatformIO, lockfiles)
  .venv/                # env Python (uv)
  config.toml           # config optionnelle (paths, Bitwig)
```

Notes:

- Les repos requis pour build/run sont pin dans `ms/data/repos.toml`.
- Pour un workspace "maintainer" (distribution + ms-manager + extras), utiliser `ms/data/repos.maintainer.toml` via `uv run ms sync --repos --profile maintainer`.
- Les versions toolchains sont pin dans `ms/data/toolchains.toml`.

### Bundled vs system deps

Bundlés via `ms sync --tools` (dev) :

- CMake, Ninja
- Zig (Windows)
- Emscripten (WASM)
- JDK + Maven (Bitwig extension)
- PlatformIO (venv dans `tools/platformio/venv`)

Système (guidé par `ms prereqs` / `ms check`) :

- `uv` (prérequis pour lancer `ms`)
- `git` (requis pour sync repos, mais installable/guidable)
- libs build natives (Linux) : SDL2, ALSA, libudev, pkg-config, toolchain C/C++
- macOS : Xcode CLT (SDL2 optionnel; fallback FetchContent côté CMake)

## CI (actuel)

Il y a 2 workflows distincts :

- `.github/workflows/ci.yml` (push/PR): tests/typing + smoke CLI en dry-run
  - matrice runners: ubuntu / windows / macos
  - Fedora: job séparé en container (pas de runner fedora GitHub-hosted)

- `.github/workflows/builds.yml` (schedule + manual): builds réels
  - native: Windows/macOS/Linux
  - wasm: Ubuntu uniquement
  - Pages: déploie les artefacts WASM sous `/demo/<app>/latest/`

## Distribution (implémentée)

### Objectif

Un seul contrat, trois canaux: un manifest signé décrit exactement les assets installables.

- Repo source-of-truth: `petitechose-midi-studio/distribution` (GitHub Releases + Pages).

- Canaux:
  - `nightly`: pré-release (automatique, skip si pas full green)
  - `beta`: pré-release (manual)
  - `stable`: release (manual)

### Manifest (contrat end-user)

Le manifest (schema=2) inclut :

- `channel` (`stable|beta|nightly`) + `tag`
- `repos[]` (pins des SHAs pour audit)
- `assets[]` (size + sha256) + `install_sets[]` (profiles)
- signature Ed25519 (`manifest.json.sig`)

Optimisation locked:
- stable/beta: reuse par copie (tags self-contained)
- nightly: reuse via `assets[].url` (même canal uniquement)

## Installer end-user (implémenté progressivement)

### Objectif

Une app end-user (`ms-manager`, Tauri) qui :

- permet de choisir un canal (stable/beta/nightly) + une version (par défaut: stable + latest)
- installe / met à jour / désinstalle les binaires finaux uniquement
- gère l'intégration OS (raccourcis + bridge service)

### Intégration bridge service

Le bridge (`oc-bridge`) fournit des primitives (service name + exec override + ctl pause/resume).

Pour fiabilité/atomicité, la gestion de service et des upgrades doit être orchestrée par un helper (`ms-updater`)
plutôt que de dépendre uniquement des commandes `oc-bridge install/uninstall`.

## Source de vérité

- CLI: `uv run ms --help`
- CI: `.github/workflows/ci.yml`, `.github/workflows/builds.yml`
- Roadmap exécutable: `docs/memories/work/ms-user-release-workflow/README.md`
