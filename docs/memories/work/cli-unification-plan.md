# CLI Unification Plan (DEV First)

> Date: 2026-01-25
> Statut: DRAFT (a valider ensemble)

Objectif: faire de `ms/` l'unique systeme (CLI + setup + checks + toolchains + repos + builds), supprimer definitivement tout legacy (`ms_cli/`, wrappers historiques, scripts dupliques), et garantir un design clean, multiplateforme, maintenable.

Deroule d'execution (ordre exact, runbook): `docs/memories/work/cli-unification-execution.md`

Scope immediat: **mode DEV uniquement**.
Scope differe: mode END-USER (GitHub Releases) - on prepare l'architecture pour l'ajouter sans refonte.


## Definition of Done

- Un seul backend: tout comportement vit dans `ms/` (pas de duplication ailleurs).
- Un seul point d'entree documente: `uv run ms ...` depuis la racine workspace.
- `ms setup` est l'orchestrateur unique du mode dev (repos + toolchains + activation + verification + builds optionnels).
- `ms check` est la source de verite (mode-aware) et donne des hints actionnables.
- `ms build/upload/monitor/run/web/clean/bridge/icons/status/update` existent en version dev et appellent les services `ms/services/*`.
- Les scripts shell restants sont uniquement des bootstrap minimaux (si conserves) et ne contiennent aucune logique metier.
- `ms_cli/` supprime.
- CI: tests + pyright strict sur `ms/` et smoke tests sur `uv run ms check`.


## Decisions fermes (pas d'ambiguite)

- **CLI unique**: `ms` (package `ms/`).
- **Execution canonique (cross-platform, sans activation)**: `uv run ms <command>`.
- **Alias non-invasif (optionnel)**: `tools/activate.*` peut mettre `ms` dans le PATH (via `tools/bin`).
- **Mode dev**: dependance assumee sur `gh` (GitHub CLI, authentifie) + `git`.
- **Bridge (Windows, DEV)**: build-from-source requis -> `rustup` + MSVC Build Tools (C++ build tools + Windows SDK). Pas besoin de l'IDE Visual Studio.
- **Repos dev**: discovery via GH API (default branch, pas hardcode "main"), clone/update idempotent.
- **Toolchains dev**: installees et gerees par `ms.tools` (cache + state + wrappers + activation scripts).
- **Non invasif par defaut**: aucune ecriture automatique dans `.bashrc`/PowerShell profiles; uniquement `tools/activate.*`.
- **DIP strict**: output, HTTP, command runner, filesystem access injection-friendly.
- **Qualite**: pyright strict, tests unitaires + tests d'integration (sans reseau si possible, via mocks).


## UX/DX principles (cible)

- One-liner mental model: `ms setup` -> `ms check` -> `ms build/upload/run/web`.
- Idempotent: relancer `ms setup` ne casse rien, ne reinstalle pas inutilement.
- Fast default: caches (downloads), skip des repos dirties, ff-only par defaut.
- Non invasif: aucune modification systeme silencieuse; tout ce qui est "system-level" passe par `ms check` + instructions.
- Reproductible: versions toolchains pinnees + snapshot repos resolus (lock) a chaque sync.
- Observable: `--dry-run` sur toutes les commandes qui modifient (repos/tools/setup/update), + `--verbose`.


## Reproductibilite (DEV)

Repos:
- Par defaut: on suit la default branch de chaque repo (latest), mais on ecrit toujours un snapshot `.ms/repos.lock.json` (repo -> remote -> default_branch -> sha).
- On ignore les repos archives.
- Option future (si besoin): filtrer par topics (ex: `ms-workspace`) pour ne pas cloner des repos hors scope.
- Option de reproduction exacte: `ms repos sync --lock .ms/repos.lock.json` (checkout SHAs).

Toolchains:
- Par defaut: versions pinnees dans un fichier versionne (ex: `ms/data/toolchains.toml`).
- Action explicite: `ms tools upgrade` met a jour les pins (et doit etre committe si on veut un "known good").
- `ms tools sync` installe uniquement ce qui manque ou ce qui ne match pas la version pinnee.


## Strategie Windows (DEV)

Objectif: maximiser "pas de VS" sans sacrifier la stabilite.

- Teensy (PlatformIO): VS non requis.
- WASM (emsdk): VS non requis.
- Native SDL:
  - Windows: utiliser Zig via `CMAKE_TOOLCHAIN_FILE` (pas MSVC) + SDL2 bundle.
  - Linux/macOS: SDL2 via deps systemes (check + hint).
- Bridge (Rust): point dur.
 - Bridge (Rust): requis en mode dev.
   - Windows: **MSVC Build Tools requis** (C++ build tools + Windows SDK) + `rustup` (rustc/cargo).
   - VS-free sur Windows (mingw/zig linker) = option avancée, a considerer plus tard.


## Architecture cible (monosource)

Principes:
- `ms/cli`: Typer uniquement, pas de logique metier.
- `ms/services`: orchestration (setup/check/build/update/repos/tools).
- `ms/tools`: toolchains (download/install/state/wrappers).
- `ms/git`: multi-repo.
- `ms/core`: workspace/config/codebase/result/errors.
- `ms/platform`: detection + shell activation.

Structure cible (simplifiee):

```
ms/
  __init__.py
  __main__.py
  cli/
    app.py
    context.py
    commands/
      setup.py
      check.py
      repos.py
      tools.py
      build.py
      bridge.py
      update.py
      status.py
      icons.py
  core/
  platform/
  output/
  tools/
  git/
  build/
  services/
    checkers/
    setup.py
    repos.py
    toolchains.py
    build.py
    bridge.py
    update.py
```


## Workspace layout (prepare END-USER sans l'implementer)

On separe strictement code et state.

Workspace marker (versionne): ajouter un fichier `.ms-workspace` (vide) a la racine.
- But: detection workspace sans dependre d'un dossier `commands/` (legacy).
- Consequence: on pourra supprimer `commands/` totalement a la fin.

- `.ms/` (workspace state, non versionne)
  - `.ms/state.toml` (mode, options, timestamps)
  - `.ms/repos.lock.json` (snapshot des SHAs resolus)
  - `.ms/cache/` (downloads cache pour ms)
- `tools/` (toolchains installees, non versionne)
  - `tools/bin` (wrappers)
  - `tools/state.json` (versions toolchains installees)
- `bin/` (artefacts de build, non versionne)
- `.build/` (build artifacts, non versionne)

END-USER plus tard: ajouter `bin/releases/` + manifest sans casser l'arborescence.


## Contrat des commandes (mode DEV)

- `ms setup`:
  - interactif si pas de flags: propose `dev` vs `enduser` (enduser = "not implemented" pour l'instant).
  - `--mode dev` (default tant que enduser pas implemente)
  - orchestre: repos -> toolchains -> activation -> check -> (optionnel) builds.

- `ms check`:
  - verifie workspace (repos), toolchains (ms.tools), prerequis systeme (SDL2/ALSA/etc), runtime.
  - doit etre idempotent et "actionnable".

- `ms repos sync`:
  - utilise `gh` pour lister les repos, clone la default branch, update ff-only.
  - ecrit `.ms/repos.lock.json` (repo -> remote -> branch -> sha).

- `ms tools sync`:
  - installe toolchains requises pour DEV via `ms.tools`.
  - genere `tools/activate.*`.

- `ms build <codebase> <target>`:
  - `target`: `teensy|native|wasm`.
  - par defaut, teensy delegue a OpenControl (`oc-build/oc-upload/oc-monitor`).

- `ms upload/monitor/run/web/clean`:
  - wrappers ergonomiques sur BuildService.

- `ms bridge build/run`:
  - build et run `open-control/bridge`.

- `ms update`:
  - dev: update explicite (repos ff-only, toolchains upgrade explicite, python deps).

- `ms status`:
  - git multi-repo (workspace + open-control/* + midi-studio/*).


## Plan d'action (ordre d'execution)

### Phase 1 - Fixer le contrat et preparer la base (no behavior change)

1) Ajouter `.ms-workspace` (marker) et migrer `ms.core.workspace.detect_workspace()` pour l'utiliser.
2) Creer le state workspace `.ms/state.toml` (mode-aware) et `.ms/cache/`.
3) Ajouter un `RepoService` (API, pas encore branche sur `ms setup`).
4) Ajouter un `ToolchainService` (API, pas encore branche sur `ms setup`).
5) Creer le squelette CLI `ms/cli` + wiring DI (Console, Workspace, Config, Platform, Runner).
6) Ajouter `ms setup` (stub) + `ms check` (appelle checkers existants).

Critere: `uv run ms --help`, `uv run ms check` fonctionnent en ne cassant rien.


### Phase 2 - Repos DEV via GH (ms devient source de verite)

1) Implementer `ms repos sync`:
   - require `gh` + `gh auth status`.
   - lister repos des orgs (open-control, petitechose-midi-studio).
   - cloner dans `open-control/<repo>` ou `midi-studio/<repo>`.
   - cloner la **default branch** (pas hardcode main).
   - update: ff-only si clean.
   - ecrire `.ms/repos.lock.json`.
2) Integrer `RepoService` dans `ms setup --mode dev`.

Critere: un clone vide du workspace + `uv run ms repos sync` produit l'arborescence complete.


### Phase 3 - Toolchains DEV via `ms.tools` (pinned, reproductible)

1) Definir une source de verite "versions toolchains" (fichier versionne dans ce repo):
   - ex: `ms/data/toolchains.toml` (versions pinnees).
2) Implementer `ms tools sync`:
   - installe les outils requis pour Mode.DEV via `ToolRegistry`.
   - applique les versions pinnees.
   - download cache dans `.ms/cache/`.
   - state dans `tools/state.json`.
   - genere `tools/activate.*`.
3) Implementer `ms tools upgrade` (action explicite) pour rafraichir les versions.
4) Integrer `ms tools sync` dans `ms setup --mode dev`.

Critere: `uv run ms tools sync` installe un environnement dev coherent sans toucher aux profiles shell.


### Phase 4 - Portage builds dans `ms/` (supprimer dependance a `ms_cli/build`)

1) Creer `ms/build/teensy.py`, `ms/build/native.py`, `ms/build/wasm.py` en portant le code de `ms_cli/build/*`.
2) Adapter pour utiliser `ms.tools` (ToolRegistry/Resolver) + Runner injectable.
3) Teensy:
   - par defaut: delegation a `open-control/cli-tools/bin/oc-*`.
   - fallback "raw": `pio` direct.
4) Native:
   - Windows: utiliser Zig comme toolchain (pas VS) via `CMAKE_TOOLCHAIN_FILE`.
   - SDL2: Windows via tool bundled; Linux/mac via system deps (check + hint).
5) WASM:
   - emsdk via `ms.tools` (non global), run emcmake/emcc via python.
6) Exposer `ms build/run/web/upload/monitor/clean` via `ms/services/build.py`.

Critere: `uv run ms build core teensy`, `uv run ms run core`, `uv run ms web core` fonctionnent (selon OS deps).


### Phase 5 - Orchestration DEV complete (`ms setup` devient le seul setup)

1) Implementer `SetupService`:
   - etapes: repos sync -> tools sync -> activation scripts -> check -> (optionnel) build bridge/bitwig.
   - flags: `--skip-repos`, `--skip-tools`, `--skip-check`, `--targets teensy,native,wasm,bridge`.
2) Ajouter un mode interactif minimal:
   - prompt: dev vs enduser (enduser non implemente => message clair).
   - prompt optionnel: targets.
3) Verrouiller le comportement idempotent.

Critere: sur machine fraiche, `uv run ms setup --mode dev` suffit pour etre operationnel.


### Phase 6 - Bridge + Bitwig (DEV)

1) `BridgeService`:
   - build `open-control/bridge` (cargo) + run.
   - Windows: strategy explicite (VS-free si possible, sinon prerequis documente + check).
2) `BitwigService`:
   - build/deploy extension via Maven/JDK geres par tools.
   - discovery du dossier Bitwig + override config.

Critere: `uv run ms bridge` et `uv run ms setup` (avec bitwig) fonctionnent.


### Phase 7 - Switch final + suppression legacy (un seul systeme)

1) Basculer le script entrypoint `ms` vers `ms.cli.app:main` dans `pyproject.toml`.
2) Supprimer `ms_cli/` et toutes references.
3) Supprimer tout le legacy repo-level:
   - `commands/` (wrappers, dev scripts, completions)
   - scripts de setup legacy (tout ce qui n'est pas un bootstrap minimal)
   - toute reference a `ms_cli`.
4) Transformer `setup-minimal.sh` en bootstrap minimal:
   - il ne clone plus les repos.
   - il ne fait que: verifier `uv` puis lancer `uv run ms setup --mode dev`.
   - ajouter un equivalent PowerShell si necessaire (strictement minimal).
5) Mettre a jour docs (README) avec un unique chemin.

Critere: aucun fichier legacy ne reste; un nouveau clone suit un seul chemin documente.


## Test & CI (quality gate)

- Unit tests: `uv run pytest ms/test -q`
- Typecheck: `uv run pyright ms`
- Smoke:
  - `uv run ms --help`
  - `uv run ms check`
  - `uv run ms repos sync --dry-run` (a ajouter)
  - `uv run ms tools sync --dry-run` (a ajouter)


## END-USER (differe, mais prepare)

Ce qu'on fait maintenant pour faciliter l'ajout plus tard:
- `Mode` existe deja (`DEV`, `ENDUSER`).
- Workspace state `.ms/state.toml` prevoit `mode` + `channel/ref`.
- Services separables: RepoService/ToolchainService/BuildService.

Plus tard (hors scope): `ReleaseService` (GitHub Releases manifest + download + history + pin/rollback).
