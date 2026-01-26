# MIDI Studio Workspace CLI - Unification + Parite (DEV First)

> Start date: 2026-01-25
> Last updated: 2026-01-25
> Status: ACTIVE (source of truth)
> Scope: DEV only. END-USER is deferred.

Objectif: faire de `ms/` l'unique systeme (CLI + setup + checks + toolchains + repos + builds), supprimer definitivement tout legacy (`ms_cli/`, `setup.sh`, docs legacy), et restaurer toutes les fonctionnalites utiles de l'ancien CLI via des equivalents propres et maintenables.

Runbook (procedure de validation, dont "fresh workspace"): `docs/memories/work/cli-unification-execution.md`


## Etat actuel (factuel)

Livre (deja fait, dans le repo):

- Backend unique: `ms/` (services, outils, checkers, tests).
- Point d'entree officiel: `uv run ms <cmd>` (pas d'activation requise).
- Workspace marker: `.ms-workspace`.
- State: `.ms/` (gitignored) + build: `.build/` + runtime artifacts: `bin/` + toolchains: `tools/`.
- Commandes existantes:
  - `ms setup --mode dev` (repos + tools + python deps + check)
  - `ms check`
  - `ms repos sync`
  - `ms tools sync`
  - `ms bridge build/run`
  - `ms bitwig build/deploy`
  - `ms build/run/web` (native + wasm)
- Decisions actees:
  - `uv` est une dependance systeme (pas installee/upgradee par `ms`).
  - Pas de modification automatique des profiles shell; uniquement `tools/activate.*`.
  - PlatformIO est isole dans le workspace via `PLATFORMIO_*` + venv dediee.
- Legacy supprime:
  - `ms_cli/`
  - `setup.sh`
  - `docs/ms-cli/`

Non livre (a faire pour parite):

- Commandes restantes: upload/monitor/clean/update/status/changes/icons/completion/list.
- `build/run` existent mais Windows native doit etre simplifie (cf. Phase B.1).
- Orchestration optionnelle (si desire): `ms setup` peut declencher `bridge/bitwig` via flags.
- CI moderne (tests + pyright + smoke) sans `setup.sh`.


## Definition of Done (parite DEV)

On considere l'objectif atteint quand:

- `ms/` est l'unique backend (aucune logique metier ailleurs).
- `uv run ms ...` est l'unique point d'entree documente (le reste est optionnel et deprecie).
- "Fresh workspace" reproductible:
  - suppression de `open-control/`, `midi-studio/`, `tools/`, `.ms/`, `.build/`, `bin/`, `.venv/`
  - `uv run ms setup --mode dev` reconstruit repos + toolchains + deps Python + scripts d'activation
  - `uv run ms check` est actionnable (0 erreurs bloquantes; warnings acceptes selon prerequis externes).
- Parite commandes legacy (equivalents dans `ms`):
  - `ms bridge build/run`
  - `ms bitwig build/deploy`
  - `ms build/upload/monitor/run/web`
  - `ms clean`
  - `ms update`
  - `ms status` / `ms changes`
  - `ms icons`
  - `ms completion`
  - `ms list`
- Tests/quality gate:
  - `uv run pytest ms/test -q`
  - `uv run pyright ms --stats`
  - smoke: `uv run ms --help`, `uv run ms check`


## Decisions actees (et leur impact)

1) `uv` = dependance systeme
- Raison: bootstrap stable, evite overwrite/locks Windows, moins de matrice plateforme.
- Consequence: `ms check` doit expliquer comment installer/upgrade `uv`.

2) `gh` (auth) = dependance DEV
- Raison: discovery repos via API + HTTPS.
- Consequence: `ms repos sync` echoue si `gh` absent/non-auth.

3) PlatformIO isole (workspace-local)
- Env vars forcees:
  - `PLATFORMIO_CORE_DIR=.ms/platformio`
  - `PLATFORMIO_CACHE_DIR=.ms/platformio-cache`
  - `PLATFORMIO_BUILD_CACHE_DIR=.ms/platformio-build-cache`
- Consequence: pas de pollution `~/.platformio`.

4) Non invasif par defaut
- Pas d'ecriture dans `.bashrc`/PowerShell profiles.
- On genere seulement `tools/activate.*`.

5) Windows: eviter WMI pour la detection
- Raison: `platform.system()`/`platform.machine()` peut hang sur certains environnements Windows.
- Consequence: detection via `sys.platform` + env vars processeur.

6) Windows native: MSVC (Build Tools) uniquement
- Objectif: toolchain plateforme-native, robuste, et suppression du glue code Zig.
- Consequence:
  - `zig` n'est plus requis/installe par `ms tools sync` (sauf reintroduction explicite plus tard).
  - Windows native build exige Visual Studio Build Tools 2022 (workload C++).
  - SDL2 Windows: utiliser le package `SDL2-devel-<ver>-VC.zip` (pas MinGW).
  - `ms build <codebase> native` sur Windows utilise le generateur CMake "Visual Studio 17 2022".


## Incoherences / dette technique identifiees (a corriger)

- `--dry-run` n'est pas encore "zero side effects":
  - `ms tools sync --dry-run` cree quand meme `tools/` et `tools/bin/`.
  - `ms repos sync --dry-run` appelle `gh repo list` (reseau).
- `ms check` Runtime hint: `ms bridge install` est mentionne mais la commande n'existe pas encore.
- `ms check` depend du `uv` trouve dans PATH; l'environnement shell (PowerShell vs Git Bash) peut changer le binaire resolu.


## Inventaire parite (legacy -> nouveau)

Source legacy: ancien `ms` (Typer) + scripts `open-control/cli-tools`.

| Legacy | Nouveau (cible) | Statut | Notes |
|---|---|---|---|
| `ms doctor` | `ms check` | DONE | `ms check` remplace doctor/verify en unifie. |
| `ms verify` | `ms check` | DONE | (Option: ajouter `ms verify` alias si besoin). |
| `ms setup --bootstrap` | `ms setup --mode dev` | DONE | Aujourd'hui: prepare workspace (pas de builds projet). |
| `ms setup` (build bridge + deploy bitwig) | `ms bridge build` + `ms bitwig deploy` | DONE | Decision actee: build/deploy sont des commandes explicites (pas implicitement dans `ms setup`). |
| `ms update` | `ms update` | TODO | Subcommands/flags a definir, mais parite requise (repos/tools/python). |
| `ms status` / `ms changes` | `ms status` / `ms changes` | TODO | Git multi-repo (workspace + children). |
| `ms list` | `ms list` | TODO | Liste codebases (core + plugin-*). |
| `ms completion` | `ms completion bash|zsh` | TODO | Ideal: generer depuis Typer, ou servir les fichiers. |
| `ms icons <core|bitwig>` | `ms icons <core|bitwig>` | TODO | Appel a `open-control/ui-lvgl-cli-tools/icon/build.py`. |
| `ms build <codebase> [native|wasm|teensy]` | `ms build ...` | PARTIAL | Fonctionnel (native+wasm) mais Windows native doit etre simplifie (MSVC, cf. Phase B.1). |
| `ms run <codebase>` | `ms run <codebase>` | PARTIAL | Fonctionnel; depend de la stabilite build native Windows (cf. Phase B.1). |
| `ms web <codebase>` | `ms web <codebase>` | DONE | Build wasm + serve. |
| `ms upload <codebase>` | `ms upload <codebase>` | TODO | Teensy upload. |
| `ms monitor <codebase>` | `ms monitor <codebase>` | TODO | Teensy monitor. |
| `ms clean [codebase]` | `ms clean [codebase]` | TODO | Ne pas supprimer `bin/bridge`. |
| `ms bridge [args...]` | `ms bridge run [args...]` | TODO | Preferer `bin/bridge/` si present. |
| `ms core` / `ms bitwig` (quick upload) | `ms core` / `ms bitwig` (alias) | OPTIONAL | DX only; peut etre conserve. |
| `ms r/w/b` aliases | `ms r/w/b` aliases | OPTIONAL | DX only; peut etre conserve. |


## Roadmap (phases, sans ambiguite)

### Phase A - Parite "Bridge" + "Bitwig" (restaurer setup projet)

Livrables:
- `ms bridge build` (release) + copie vers `bin/bridge/` (binaire + config)
- `ms bridge run` (exec)
- `ms bitwig build` + `ms bitwig deploy` (detect Extensions dir via config/defaults)
- Mise a jour `ms check` hints pour pointer vers ces commandes (plus de hints inexistants)

Statut: DONE (valide sur Windows)

Acceptance:
- `uv run ms bridge build` produit `bin/bridge/oc-bridge(.exe)`
- `uv run ms bridge run --help` (ou args) lance le binaire
- `uv run ms bitwig deploy` produit `bin/bitwig/*.bwextension` et installe dans le dossier Extensions

Prerequis:
- Rust/cargo (system)
- Maven/JDK fournis via `ms tools sync`

### Phase B - Parite "native" + "wasm" (build/run/web)

Livrables:
- `ms build <codebase> native`
- `ms run <codebase>`
- `ms build <codebase> wasm`
- `ms web <codebase> [--port] [--no-watch]`

Notes:
- Native toolchains par plateforme (cible finale):
  - Windows: MSVC (Visual Studio Build Tools 2022)
  - Linux: GCC/Clang system
  - macOS: Xcode Clang
- WASM: Emscripten via `tools/emsdk` (toutes plateformes).

Statut:
- WASM: DONE
- Native:
  - Linux/macOS: OK
  - Windows: a migrer Zig -> MSVC (cf. Phase B.1)

### Phase B.1 - Windows native simplification (Zig -> MSVC, zero workaround)

Objectif:
- Utiliser une toolchain "plateforme-native" (MSVC) et supprimer les workarounds (wrappers zig, toolchain file, `-j1`, etc.).
- Reduire `ms/services/build.py` a une orchestration CMake standard.

Non-objectifs (assumes):
- Pas de support MinGW sur Windows.
- Pas de cross-compilation Windows via Zig.
- SDL reste en v2 (LVGL/stack actuelle).

Invariants (ce qui ne change pas):
- Entry point: `uv run ms ...`
- Layout artifacts: `.build/<app_id>/{native,wasm}` et `bin/<app_id>/{native,wasm}`
- WASM: `emcmake` + Ninja.
- PlatformIO: `.pio/libdeps` reste source LVGL.

Plan d'execution (ultra precis, sans ambiguite)

1) Decision: generator CMake (Windows native)
- Windows native: `cmake -G "Visual Studio 17 2022" -A <arch>`
- Build: `cmake --build <build_dir> --config Release`
- Raison: aucune dependance a l'environnement vcvars (pas besoin de "Developer Prompt"), robuste dans tous les shells.

2) SDL2 Windows: passer du bundle MinGW a VC
- Changer le download asset:
  - avant: `SDL2-devel-<ver>-mingw.zip`
  - apres: `SDL2-devel-<ver>-VC.zip`
- Adapter la verification d'installation: presence d'un artefact stable (ex: `cmake/sdl2-config.cmake` ou `lib/x64/SDL2.lib`).
- Adapter les chemins exposes par l'outil (include/lib) si utilises par d'autres composants.

Fichiers:
- `ms/tools/definitions/sdl2.py`

Acceptance:
- `uv run ms tools sync` installe SDL2 Windows en mode VC (pas de `x86_64-w64-mingw32/`).

3) CMake (projet midi-studio): utiliser SDL2 via find_package (pas de libs hardcode)
- Dans `midi-studio/core/sdl/CMakeLists.txt`:
  - supprimer l'import manuel `add_library(SDL2-static STATIC IMPORTED ...)`
  - sur Windows, quand `SDL2_ROOT` est fourni:
    - ajouter `${SDL2_ROOT}` au `CMAKE_PREFIX_PATH` (ou definir `SDL2_DIR`), puis `find_package(SDL2 REQUIRED)`
    - lier via une target de package (ex: `SDL2::SDL2-static` si dispo, sinon `SDL2::SDL2`)
  - supprimer le flag MinGW `-mconsole`.

Fichiers:
- `midi-studio/core/sdl/CMakeLists.txt`

Acceptance:
- CMake configure + build sur Windows/MSVC sans referencer `.a` ou `mingw32`.

4) BuildService: supprimer Zig et unifier sur CMake standard
- Dans `ms/services/build.py`:
  - supprimer toute la logique Zig (toolchain file, wrappers, prereqs Zig, `-j1`).
  - `build_native`:
    - Windows: generator Visual Studio (ci-dessus)
    - non-Windows: `-G Ninja` (inchangé)
    - build via `cmake --build` (toutes plateformes)
  - passer `-DSDL2_ROOT=<tools/sdl2>` sur Windows native (pour que CMake trouve SDL2 bundled).
  - conserver `pio pkg install` auto (necessaire a LVGL) mais documenter que c'est un effet de bord du build.

Fichiers:
- `ms/services/build.py`

Acceptance:
- `uv run ms build core native` produit `bin/core/native/midi_studio_core.exe`
- `uv run ms build bitwig native` produit `bin/bitwig/native/midi_studio_bitwig.exe`
- `uv run ms run core` et `uv run ms run bitwig` lancent les exe.

5) Checks: prerequis compilateur par plateforme
- `ms check` doit etre actionnable et dire quoi installer.

Windows:
- Detecter Visual Studio Build Tools 2022 via `vswhere.exe` (path standard) + composant C++.
- Si absent: erreur bloquante pour "native build" (mais pas pour wasm).

Linux:
- Detecter un compilateur (`cc`/`c++` ou `gcc`/`g++` ou `clang`/`clang++`).
- Hint minimal: `sudo apt install build-essential pkg-config libsdl2-dev` (adapter par distro si on veut).

macOS:
- Detecter Xcode CLT (`xcode-select -p` ou `clang`).
- Hint: `xcode-select --install`.

Fichiers:
- `ms/services/checkers/system.py` (ou nouveau checker dedie MSVC)
- `ms/services/check.py` (si besoin de wiring)

Acceptance:
- `uv run ms check`:
  - Windows: affiche "MSVC: ok" si Build Tools present.
  - Linux/macOS: affiche "C/C++ compiler: ok" (ou hint clair si manquant).

6) Tools: retirer Zig de la toolchain DEV
- Retirer `zig` des tools bundles et des wrappers.

Fichiers:
- `ms/tools/definitions/zig.py` (supprimer)
- `ms/tools/definitions/__init__.py` (retirer import/export/ALL_TOOLS)
- `ms/services/checkers/tools.py` (retirer ZigTool du check)
- `ms/tools/wrapper.py` (retirer generation wrappers zig-cc/zig-cxx/zig-ar)
- `ms/services/toolchains.py` (retirer references)
- tests associes (voir point suivant)

Acceptance:
- `uv run ms tools sync` n'installe plus `tools/zig/`.
- `uv run ms check` ne mentionne plus Zig.

7) Tests: mettre a jour suite a la suppression Zig
- Supprimer/adapter tous les tests qui attendent Zig/wrappers.

Fichiers:
- `ms/test/tools/definitions/test_zig.py` (supprimer)
- `ms/test/tools/test_wrapper.py` (retirer cas zig-*)
- `ms/test/test_integration_phase2.py` (retirer expectations zig)
- `ms/test/tools/definitions/test_init.py` (retirer ZigTool)

Acceptance:
- `uv run pytest ms/test -q` (pass)
- `uv run pyright ms --stats` (0 errors)

8) Nettoyage repo + docs
- Mettre a jour `docs/memories/work/cli-unification-execution.md` (prerequis Windows native = Build Tools)
- Supprimer toute reference docs a Zig comme prerequis.

Acceptance:
- Fresh workspace (Windows) + `uv run ms setup --mode dev` n'installe pas Zig.
- `uv run ms build core native` marche apres installation Build Tools.

### Phase C - Parite Teensy (build/upload/monitor)

Approche (deux etapes, explicite):
- Etape 1 (parite rapide): utiliser `open-control/cli-tools/bin/oc-build|oc-upload|oc-monitor` quand `bash` est disponible (Git Bash sur Windows), sinon fallback `--raw`.
- Etape 2 (maintenabilite): reimplementer le workflow en Python (spinner/memory bars optionnels).

Livrables:
- `ms build <codebase> teensy [--release] [--raw]`
- `ms upload <codebase> [--release] [--raw]`
- `ms monitor <codebase> [--release] [--raw]`

### Phase D - Hygiene UX (update/status/clean/icons/completion/list)

Livrables:
- `ms update` (repos/tools/python) + `--dry-run`
- `ms status` / `ms changes`
- `ms clean`
- `ms list`
- `ms icons`
- `ms completion`

### Phase E - Hardening (dry-run, CI, docs)

Livrables:
- `--dry-run` = zero side effects (idealement zero reseau)
- CI: tests + pyright + smoke `ms check`
- Doc root (README) explique 1 seul chemin: `uv run ms ...`
- Option: deprecier/supprimer `commands/` wrappers une fois `ms completion` stable


## Validation "fresh workspace" (deja executee)

Machine: Windows

Preconditions:
- `uv` installe
- `git` installe
- `gh` installe + `gh auth status` OK

Procedure:
1) Deplacer (backup) ou supprimer: `open-control/`, `midi-studio/`, `tools/`, `.ms/`, `.build/`, `bin/`, `.venv/`
2) Executer: `uv run ms setup --mode dev`
3) Verifier: `uv run ms check`

Resultat observe (OK):
- repos reclones
- toolchains installees (ninja/cmake/zig/bun/jdk/maven/emsdk/platformio/sdl2)
- python deps sync
- `ms check` sans erreurs bloquantes
- warnings attendus: `oc-bridge` "not built" (commande a implementer), runtime MIDI/asset tools optionnels

Note: une sauvegarde a ete creee localement lors du test: `C:\Users\simon\pc_fresh_backup_20260125-174015`
