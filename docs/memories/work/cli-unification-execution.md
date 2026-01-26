# CLI Unification - Execution Runbook (DEV)

> Last updated: 2026-01-25
> Status: ACTIVE
> Roadmap / decisions: `docs/memories/work/cli-unification-plan.md`

Ce document est une checklist operationnelle pour:

- verifier l'etat du setup DEV
- executer un test "fresh workspace" (reproductibilite)
- capturer les sorties attendues / warnings acceptables


## Preconditions (system)

Requis (DEV):

- `uv` (system dependency)
- `git`
- `gh` + `gh auth status` OK

Requis (build native):

- Windows: Visual Studio Build Tools 2022 (workload "Desktop development with C++")
- Linux: un compilateur C/C++ (gcc/g++ ou clang/clang++) + `pkg-config` + `libsdl2-dev`
- macOS: Xcode Command Line Tools (`xcode-select --install`)

Optionnel (selon ce que tu testes):

- `cargo` (bridge build)
- outils runtime: loopMIDI (Windows), inkscape/fontforge (icons)


## Canonical invocation

- Officiel: `uv run ms <cmd>`
- Optionnel: `tools/activate.*` (ajoute `tools/bin` au PATH)


## Quick smoke (sans rien casser)

Depuis la racine workspace:

1) `uv run ms --help`
2) `uv run ms check`

Attendu:

- workspace detecte via `.ms-workspace`
- hints actionnables si deps manquantes


## Setup DEV (workspace existant)

Commande:

- `uv run ms setup --mode dev`

Attendu:

- repos sync (`open-control/`, `midi-studio/`)
- toolchains installees dans `tools/` + `tools/activate.*` + `tools/bin/*`
- python deps: `uv sync --frozen --extra dev`
- `ms check` termine sans erreurs bloquantes


## Fresh workspace validation (reproductibilite)

Objectif: valider qu'un workspace vide peut etre reconstruit via `ms setup`.

1) Backup (recommande) ou suppression de:
- `open-control/`
- `midi-studio/`
- `tools/`
- `.ms/`
- `.build/`
- `bin/`
- `.venv/`

2) Run:
- `uv run ms setup --mode dev`

3) Verify:
- `uv run ms check`

Elements attendus apres setup:

- `.ms/state.toml`
- `.ms/repos.lock.json`
- `.ms/cache/downloads/*`
- `tools/activate.{sh,ps1,bat}`
- `tools/bin/*` (wrappers)
- `tools/platformio/venv/`

Warnings acceptables aujourd'hui:

- `oc-bridge: not built` (tant que tu n'as pas execute `uv run ms bridge build`)
- runtime: loopMIDI / inkscape / fontforge (optionnels)


## Project artifacts (bridge + bitwig)

Ces etapes ne font pas partie du bootstrap "env" (`ms setup`) par defaut.
Elles restaurent les fonctionnalites legacy (build bridge + extension Bitwig).

1) Bridge:
- `uv run ms bridge build`
- `uv run ms bridge run --help` (ou args)

2) Bitwig:
- `uv run ms bitwig build` (produit `midi_studio.bwextension` dans `host/target/` + copie dans `bin/bitwig/`)
- `uv run ms bitwig deploy` (installe dans le dossier Extensions + copie dans `bin/bitwig/`)


## Debug checklist

Si `ms repos sync` echoue:

- `gh auth status`
- verifier protocole git (HTTPS)

Si PlatformIO pollue `~/.platformio`:

- verifier que `tools/bin/pio*` est utilise
- verifier env vars `PLATFORMIO_CORE_DIR`, `PLATFORMIO_CACHE_DIR`, `PLATFORMIO_BUILD_CACHE_DIR`

Si versions differentes selon shell:

- `command -v uv` (PowerShell vs Git Bash)

Si build native Windows echoue:

- verifier Build Tools: `vswhere.exe` present (Visual Studio Installer)
- verifier que `uv run ms check` affiche "MSVC: ok"


## Quality gate (local, avant PR)

- `uv run pytest ms/test -q`
- `uv run pyright ms --stats`
