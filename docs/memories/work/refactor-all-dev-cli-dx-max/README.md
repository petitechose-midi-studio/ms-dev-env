# Refactor: Dev CLI DX Max (Deshellize + Bootstrap)

**Scope**: all (ms + open-control + midi-studio orchestration)
**Status**: planned
**Created**: 2026-01-27
**Updated**: 2026-01-27

## Objectif

Construire une CLI `ms`:

- propre, unifiee, coherente, safe (no destructive defaults)
- cross-platform: Windows recent, macOS recent, Ubuntu latest, Fedora latest
- setup le plus simple possible: **seul prerequis pour lancer** = `uv`
- installation guidee: si une dep manque, `ms` propose la commande exacte et peut l'executer quand c'est safe
- deshellise au maximum: `ms` ne depend d'aucun script bash pour ses workflows

## Invariants (non-negociables)

- Entree unique: `uv run ms ...`
- Pas de dossier/commande legacy (ex: `commands/`, wrappers historiques, completions legacy)
- Tout ce que `ms` execute:
  - jamais via `shell=True`
  - jamais via snippets shell arbitraires
  - uniquement via argv (list[str])
- Installation systeme: execution uniquement d'une allowlist (ex: `sudo apt install ...`, `sudo dnf install ...`, `winget install ...`, `xcode-select --install`)
- `ms clean` doit etre `--dry-run` par defaut ou demander confirmation explicite

## Contraintes & choix

### Prerequis “minimum”

- `uv` est requis pour lancer `ms`.
- `git` n'est **pas** suppose present (notamment Windows). Il devient une dep **installable/guidable**.

### Strategie “Python-first”

- Remplacer tous les workflows critiques bases sur bash par du Python (PlatformIO, orchestration, detection).
- Conserver uniquement les scripts inevitables:
  - activation d'environnement (set PATH/env dans le shell courant)
  - wrappers auto-generes si on veut une ergonomie terminal (optionnel, pas requis pour les commandes `ms`)

## Etat actuel (points bloquants)

- `ms/services/hardware.py` depend de `bash` + scripts `open-control/cli-tools/bin/oc-*`.
- `ms/services/repos.py` depend de `gh` et d'auth GH.
- `ms/services/bridge.py` depend de Rust/cargo et d'un linker C.
- `ms/services/checkers/system.py` impose Homebrew sur macOS.
- hints/erreurs pointent vers des commandes inexistantes (`ms tools sync`, `ms repos sync`, etc.)

## Roadmap de migration (bottom-up, commits atomiques)

## Docs protocol (obligatoire)

- Chaque phase a son fichier `.md` (voir liste ci-dessous).
- Chaque commit qui touche une phase doit aussi:
  - mettre a jour le fichier de phase correspondant (avancement + verifs)
  - ajouter une entree "Decision" si un choix technique est fait
  - ajouter une entree "Plan deviation" si on sort du plan (avec raison + sources)

Fichiers par phase:

- `docs/memories/work/refactor-all-dev-cli-dx-max/phase-1-deshellize.md`
- `docs/memories/work/refactor-all-dev-cli-dx-max/phase-2-bootstrap-prereqs.md`
- `docs/memories/work/refactor-all-dev-cli-dx-max/phase-3-repos-git-only.md`
- `docs/memories/work/refactor-all-dev-cli-dx-max/phase-4-bridge-prebuilt.md`
- `docs/memories/work/refactor-all-dev-cli-dx-max/phase-5-macos-without-brew.md`
- `docs/memories/work/refactor-all-dev-cli-dx-max/phase-6-cli-unified.md`
- `docs/memories/work/refactor-all-dev-cli-dx-max/phase-7-ci-matrix.md`

- `docs/memories/work/refactor-all-dev-cli-dx-max/STATUS.md` (etat global)

Chaque commit doit:

- etre testable localement (`uv run pytest` minimum)
- laisser un systeme dans un etat coherent (pas de hints fantomes)
- rester petit (une idee, un changement)

### Phase 1 — Deshellisation (priorite max)

**But**: `ms` ne depend plus de bash pour le workflow hardware.

1. Commit: `chore(repo): remove bootstrap shell entrypoints`
   - Supprimer `setup-minimal.sh`.
   - Supprimer `commands/` (wrappers + completions legacy).
   - Test: `uv run ms --help`.

2. Commit: `refactor(hardware): run PlatformIO directly (no oc-* scripts)`
   - Re-ecrire `ms/services/hardware.py`:
     - utiliser `tools/platformio/venv/.../pio` (via ToolRegistry) + env vars workspace (`Workspace.platformio_env_vars()`).
     - `build`: `pio run -e <env> -d <app_dir>`
     - `upload`: `pio run -e <env> -d <app_dir> -t nobuild -t upload`
     - `monitor`: `pio device monitor -d <app_dir> --quiet --raw` (+ option port)
   - Retirer toute reference a `bash`, `Git Bash`, `oc-build`, `oc-upload`, `oc-monitor`.
   - Test: unit tests (voir ci-dessous).

3. Commit: `feat(hardware): add env selection + defaults`
   - Ajouter `--env` (dev/release) aux commandes CLI qui appellent HardwareService.
   - Default = lire `platformio.ini` (`default_envs`) sinon `dev`.
   - Test: unit tests parsing INI.

4. Commit: `test(hardware): add cross-platform command construction tests`
   - Tests sans appeler PlatformIO reel:
     - le service construit la bonne commande + cwd + env
     - Windows: selection du bon binaire (`Scripts/pio.exe`)
     - Unix: selection (`bin/pio`)

5. Commit: `fix(platform): remove shell=True usage`
   - Modifier `ms/platform/clipboard.py` pour ne jamais utiliser `shell=True`.
   - Test: unit test simple (appel construit sans shell).

### Phase 2 — Bootstrap prereqs (uv-only launch)

**But**: `uv run ms setup` fonctionne meme si `git` manque; `ms` propose et peut installer.

6. Commit: `refactor(prereqs): require only what is needed per step`
   - Modifier `PrereqsService.ensure()` + CLI `ms prereqs`:
     - supprimer `require_gh`/`require_gh_auth`.
     - supprimer `rustc/cargo` comme prerequis bloquant.
     - `git` devient requis uniquement si `sync repos` ou `tools` (emsdk) est selectionne.

7. Commit: `feat(prereqs): install git automatically when safe`
   - Windows:
     - si `winget` present => hint `winget install --id Git.Git -e`.
     - sinon hint manuel `https://git-scm.com/download/win`.
   - macOS:
     - hint `xcode-select --install` (donne git + toolchain).
   - Ubuntu/Fedora:
     - hints `sudo apt install -y git` / `sudo dnf install -y git`.
   - Test: unit tests sur generation de hint selon plateforme.

8. Commit: `feat(install): group package installs per manager (apt/dnf/winget)`
   - Ameliorer `SystemInstaller.plan_installation()`:
     - grouper les installs par tool (un seul `apt install ...` au lieu de N).
     - deduper les paquets.
   - Test: unit tests sur grouping.

### Phase 3 — Repo sync sans gh (git-only)

**But**: sync repos deterministe, sans `gh`.

9. Commit: `feat(repos): add pinned repo manifest`
   - Ajouter `ms/data/repos.toml` avec:
     - repos requis
     - chemin de checkout
     - branche cible
     - URL HTTPS

10. Commit: `refactor(repos): sync from manifest (drop gh)`
   - Re-ecrire `ms/services/repos.py`:
     - clone/pull --ff-only
     - skip dirty repos
     - lockfile optionnel
   - Update hints: `ms sync --repos`.
   - Tests: repos locaux temporaires (clone/pull/skip).

### Phase 4 — Bridge sans Rust (prebuilt)

**But**: pas de Rust/cargo requis pour un dev setup.

11. Commit: `feat(bridge): install oc-bridge from GitHub releases`
    - Downloader d'asset par OS/arch.
    - Installer dans `bin/bridge/oc-bridge(.exe)`.
    - Copier `open-control/bridge/config` si present.
    - Tests unitaires: selection asset + erreur claire si plateforme non supportee.

12. Commit: `refactor(setup): bridge step uses installer, not cargo`
    - `ms setup` appelle `ms bridge install`.
    - `BridgeService.build` devient optionnel (build-from-source) et non requis.

### Phase 5 — macOS sans Homebrew obligatoire

**But**: setup macOS sans dependance brew (manual).

13. Commit: `refactor(system-check): do not require brew on macos`
    - `SystemChecker` macOS:
      - exiger CLT (clang) via `xcode-select`.
      - SDL2: passer en WARNING si manquant (pas ERROR).

14. Commit: `build(macos): fetch SDL2 when not found (macOS only)`
    - Dans `midi-studio/core/sdl/CMakeLists.txt`:
      - si macOS et `find_package(SDL2)` echoue => `FetchContent` SDL2 + build.
    - Test: CI macOS build native.

### Phase 6 — CLI unifiee (verbes, no ambiguities)

**But**: une seule surface stable et coherent.

15. Commit: `refactor(cli): verb-based commands`
    - Ajouter/standardiser:
      - `ms list`
      - `ms build <app> --target native|wasm|teensy`
      - `ms run <app>`
      - `ms web <app> [--port]`
      - `ms upload <app> [--env]`
      - `ms monitor <app> [--env]`

16. Commit: `refactor(cli): remove app-specific core/bitwig top-level commands`
    - Supprimer `ms core` / `ms bitwig` (ou les garder comme alias internes sans logique).

17. Commit: `fix(hints): remove phantom commands; align hints to real CLI`
    - Remplacer partout `ms tools sync` / `ms repos sync` / `ms bridge install` fantomes.

### Phase 7 — CI multi-plateforme (validation continue)

18. Commit: `ci: add smoke matrix (ubuntu/fedora/windows/macos)`
    - Etapes par OS:
      - `uv run ms setup --dry-run`
      - `uv run ms check`
      - `uv run ms sync --tools --dry-run`
      - `uv run ms build core --target wasm --dry-run`

19. Commit: `ci: add real builds where feasible`
    - Ubuntu/Fedora: installer deps systeme via apt/dnf dans CI.
    - Lancer build wasm + native.

## Tests (definition de done par phase)

- Phase 1 done:
  - `ms` ne lance jamais `bash`.
  - `ms core`/`ms bitwig` hardware path marche via PlatformIO (local).

- Phase 3 done:
  - aucune dependance a `gh`.

- Phase 4 done:
  - aucun prerequis Rust/cargo pour installer/run `oc-bridge`.

- Phase 7 done:
  - CI vert sur windows/ubuntu/fedora/macos (smoke + builds critiques).

## Notes multi-plateforme (bootstrap)

- Windows:
  - `git` absent par defaut. Preferer `winget install --id Git.Git -e` si `winget` est present.
  - Apres installation, PATH peut ne pas etre rafraichi dans le process courant.
    - Strategie: re-detecter `git.exe` via chemins connus (ex: `C:\Program Files\Git\cmd\git.exe`) avant de demander un restart.

- macOS:
  - `xcode-select --install` est interactif; si lance depuis `ms`, il faut stopper et demander a relancer `ms setup` apres installation.

- Linux (Ubuntu/Fedora):
  - Installer via `sudo apt install ...` / `sudo dnf install ...`.
  - `ms` ne doit jamais tenter d'ecrire dans `/usr` sans `sudo`.
