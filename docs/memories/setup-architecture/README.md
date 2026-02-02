# Setup & Distribution Architecture

Ce document décrit l'architecture d'installation pour :

1) le dev environment (`ms-dev-env`, bootstrap via `uv` + `ms`)
2) la distribution end-user (nightly/release + installer Rust)

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

## Distribution (à implémenter)

### Objectif

Deux canaux, un seul contrat: un manifest décrit exactement les binaires installables.

- Canal `nightly`:
  - build automatique 1x/jour uniquement si changement dans `ms-dev-env` OU dans un repo syncé (`ms/data/repos.toml`)
  - publie un manifest + assets (pré-release)

- Canal `release`:
  - déclenché manuellement
  - release unique (tag immuable) + manifest + assets

### Manifest (contrat)

Le manifest doit inclure :

- channel (`nightly`/`release`), build id (date/sha)
- sha `ms-dev-env`
- sha de chaque repo syncé (`open-control/*`, `midi-studio/*`)
- liste d'assets + sha256 (bridge, simulateurs, wasm, extension, firmware, uploader)

## Installer end-user (à implémenter)

### Objectif

Une app end-user (`ms-manager`, Tauri) qui :

- permet de choisir un canal (stable/beta/nightly) + une version (par défaut: stable + latest)
- installe / met à jour / désinstalle les binaires finaux uniquement
- gère l'intégration OS (raccourcis + bridge service)

### Intégration bridge service

Le bridge (`oc-bridge`) implémente déjà des commandes service (Windows/Linux).
L'installer doit réutiliser ces commandes plutôt que dupliquer la logique.

## Source de vérité

- CLI: `uv run ms --help`
- CI: `.github/workflows/ci.yml`, `.github/workflows/builds.yml`
- Roadmap exécutable: `docs/memories/work/ms-user-release-workflow/README.md`
