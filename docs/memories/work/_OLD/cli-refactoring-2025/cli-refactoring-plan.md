# CLI Refactoring - Plan Complet et Affine

> **Date de creation**: 2025-01-24
> **Derniere mise a jour**: 2025-01-25
> **Statut**: PHASE 1 COMPLETE - PHASE 2 COMPLETE - PHASE 3 COMPLETE (100%)
> **Participants**: Simon (owner), Claude (assistant)

---

## Table des matieres

1. [Decisions finales](#1-decisions-finales)
2. [Analyse du code existant](#2-analyse-du-code-existant)
3. [Architecture cible](#3-architecture-cible)
4. [Plan d'execution detaille](#4-plan-dexecution-detaille)
5. [Specifications techniques](#5-specifications-techniques)
6. [Questions restantes](#6-questions-restantes)
7. [Risques et mitigations](#7-risques-et-mitigations)
8. [Etat actuel](#8-etat-actuel)

---

## 1. Decisions finales

Toutes les questions ont ete resolues:

| Question | Decision | Justification |
|----------|----------|---------------|
| Scope commandes | **Tout garder** | status, changes, icons, interactive, aliases - valeur pour DX |
| End-user binaires | **Bridge + firmwares ELF (core/bitwig) + teensy.exe** | Via GitHub Releases |
| Source binaires | **GitHub Releases** | Versioning natif, API simple, gratuit |
| Versioning | **Binaires pinnes, dev tools latest** | Stabilite end-user, freshness dev |
| Shell config | **Script activation** (pas modification .bashrc) | Plus propre, reversible |
| Package name | **`ms`** | Simple, court |
| Structure repos | **Conservee** (open-control/ + midi-studio/) | Pas de changement |
| Offline mode | **Cache local v1** | Important pour fiabilite |
| Verbosite | **Niveau fixe v1** | Simplifier d'abord |
| Config user | **`~/.config/ms/config.toml`** | XDG standard, minimal (juste `mode`) |
| Tests | **`ms/test/`** (singulier) | Convention Python |
| Pytest config | **Dans `pyproject.toml`** | Centralise |
| Entry point migration | **Option A**: switch quand 100% complet | Pas de risque |
| setup.sh legacy | **Supprimer** quand Python fonctionne | setup-minimal.sh reste |

### 1.1 Decisions Phase 2 (2025-01-25)

| Question | Decision | Justification |
|----------|----------|---------------|
| Architecture tools | **Option B: Code-first** | Type-safe, IDE support, testable, SOLID |
| tools.toml | **Supprime** | Remplace par classes Python dans `definitions/` |
| Providers separes | **Non** | Logique dans fonctions `api.py` + classes Tool |
| HTTP pour tests | **HttpClient protocol injectable** | Permet mocks propres |
| APIs externes | **Fonctions dans `api.py`** | SRP, testable, reutilisable |
| Emscripten install | **Git clone + emsdk** | Methode officielle recommandee |
| PlatformIO install | **get-platformio.py** | Methode officielle recommandee |

### 1.2 Decisions Nettoyage Phase 2 (2025-01-25)

Apres evaluation du code, simplifications appliquees:

| Question | Decision | Justification |
|----------|----------|---------------|
| Protocols vs ABC | **1 ABC `Tool`** au lieu de 3 protocols | Plus simple, moins de bruit |
| GitHubTool constructeur | **Stateless** - http passe a `latest_version(http)` | Plus testable, pas d'etat |
| ResolvedTool.version | **Supprime** | Jamais utilise, code mort |
| Downloader.download_to() | **Supprime** | Pas utilise dans le flow reel |
| ToolResolver helpers | **Supprimes** (`resolve_by_name`, `is_bundled`, `is_available`) | Redondants |
| Version tracking | **state.py ajoute** | Necessaire pour "binaires pinnes" |

### 1.3 Deviations Implementation Phase 2 (2025-01-25)

Deviations justifiees par rapport au plan initial:

| Deviation | Plan | Implementation | Justification |
|-----------|------|----------------|---------------|
| BunTool | `GitHubTool` | `Tool` | Tag format `bun-v1.x.x` incompatible avec GitHubTool.download_url() |
| SystemTool | Classe abstraite | Inline dans CargoTool | YAGNI - un seul outil systeme, refactorable si besoin |
| install() custom | Methode `install()` | `get_install_commands()` | Retourne donnees au lieu d'executer = meilleure testabilite |
| shell.py | Une fonction | 4 fonctions + facade | Meilleure maintenabilite, support cmd.exe ajoute |

**Impact**: Conformite ~95%, toutes les deviations sont des ameliorations.

---

## 2. Analyse du code existant

### 2.1 Inventaire complet des fonctionnalites

#### Commandes CLI (cli.py)

| Commande | Lignes | Fonctionnalite | Migration |
|----------|--------|----------------|-----------|
| `--version` | 306-310 | Affiche version | Trivial |
| Mode interactif | 312-352 | Menu numerote, reexec | Phase 5 |
| `check` | 355-616 | Verifie env complet (260 lignes!) | Phase 4 - CheckerService |
| `changes`/`status` | 618-788 | Git status multi-repo | Phase 3 - GitService |
| `icons` | 790-816 | Generation fonts LVGL | Phase 5 |
| `run` | 819-846 | Build + run native | Phase 4 - BuildService |
| `web` | 849-880 | Build + serve WASM | Phase 4 - BuildService |
| `build` | 883-936 | Build teensy/native/wasm | Phase 4 - BuildService |
| `upload` | 939-971 | Build + upload Teensy | Phase 4 - BuildService |
| `monitor` | 974-1003 | Serial monitor | Phase 4 - BuildService |
| `clean` | 1006-1062 | Clean artifacts | Phase 4 - CleanerService |
| `list` | 1065-1073 | Liste codebases | Trivial |
| `bridge` | 1076-1100 | Lance oc-bridge | Phase 5 |
| `core`/`bitwig` | 1103-1168 | Aliases upload | Phase 5 |
| `setup` | 1171-1328 | Build bridge+ext OU bootstrap | Phase 4 - SetupService |
| `update` | 1331-1515 | Update repos/tools/python | Phase 4 - UpdaterService |
| `completion` | 1518-1540 | Shell completions | Phase 5 |
| `r`/`w`/`b` | 1543-1569 | Aliases courts | Phase 5 |

#### Helpers CLI (cli.py)

| Fonction | Lignes | Usage | Migration |
|----------|--------|-------|-----------|
| `workspace_root()` | 42-55 | Detection workspace | Phase 1 - Workspace |
| `run_subprocess()` | 58-71 | Execute commande | Phase 1 - Utils |
| `get_bin_root/build_root()` | 74-81 | Paths standard | Phase 1 - Workspace |
| `get_tools()` | 84-86 | Factory ToolResolver | Phase 2 - Registry |
| `run_live()` | 89-92 | Execute avec output | Phase 1 - Utils |
| `which()` | 95-96 | Trouve executable | Stdlib |
| Git helpers | 104-296 | Parse status, pull, etc. | Phase 3 - GitService |
| `check_cmd/tool/path()` | 204-259 | Verification outils | Phase 4 - CheckerService |

#### Bootstrap (setup_bootstrap.py)

| Fonction | Lignes | Usage | Migration |
|----------|--------|-------|-----------|
| `download_file()` | 51-56 | HTTP download | Phase 2 - Downloader |
| `extract_archive()` | 59-90 | tar/zip extract | Phase 2 - Installer |
| `get_github_latest_release()` | 105-111 | GitHub API | Phase 2 - api.py |
| `fetch_json()` | 114-118 | HTTP JSON | Phase 2 - HttpClient |
| `get_arch()` | 126-135 | Detection arch | Phase 1 - Platform |
| `setup_cmake()` | 143-180 | Install CMake | Phase 2 - CMakeTool |
| `setup_ninja()` | 183-215 | Install Ninja | Phase 2 - NinjaTool ✅ |
| `setup_zig()` | 218-270 | Install Zig | Phase 2 - ZigTool |
| `setup_bun()` | 463-502 | Install Bun | Phase 2 - BunTool |
| `setup_jdk()` | 505-541 | Install JDK | Phase 2 - JdkTool |
| `setup_maven()` | 544-581 | Install Maven | Phase 2 - MavenTool |
| `setup_sdl2_windows()` | 584-625 | Install SDL2 | Phase 2 - Sdl2Tool |
| `setup_emscripten()` | 628-662 | Install emsdk | Phase 2 - EmscriptenTool |
| `setup_platformio()` | 665-696 | Install PIO | Phase 2 - PlatformioTool |
| `_write_wrapper()` | 304-335 | Genere wrapper | Phase 2 - WrapperGenerator |
| `_create_zig_wrappers()` | 273-301 | Wrappers zig-cc | Phase 2 - ZigTool |
| `create_tool_wrappers()` | 389-460 | Tous les wrappers | Phase 2 - WrapperGenerator |
| `check_system_deps()` | 704-732 | Verifie SDL2/ALSA | Phase 4 - CheckerService |
| `configure_shell()` | 766-799 | Config .bashrc | Phase 2 - shell.py |
| `verify_installation()` | 926-963 | Verifie tools | Phase 4 - CheckerService |
| `run_bootstrap()` | 971-1081 | Orchestration | Phase 4 - SetupService |

#### Tools (tools.py)

| Methode | Lignes | Particularite |
|---------|--------|---------------|
| `cmake()` | 47-54 | bundled: cmake/bin/cmake |
| `ninja()` | 56-63 | bundled: ninja/ninja |
| `pio()` | 65-74 | ~/.platformio/penv/bin/pio |
| `cargo()` | 76-78 | system only |
| `mvn()` | 80-89 | bundled + allow_cmd |
| `java()` | 91-98 | bundled: jdk/bin/java |
| `zig()` | 100-107 | bundled: zig/zig |
| `zig_cc/cxx()` | 109-119 | wrappers speciaux |
| `bun()` | 121-128 | bundled: bun/bun |
| `emcmake/emcc()` | 130-142 | emsdk/upstream/emscripten/ |
| `python()` | 144-163 | venv ou bundled |
| `oc_build/upload/monitor()` | 165-178 | scripts optionnels |
| `bash()` | 180-213 | Git Bash sur Windows |
| `sdl2_dir()` | 215-220 | Windows only |

### 2.2 Patterns a eliminer

#### Pattern 1: Try/except repete 8 fois

```python
# Actuel (8 occurrences)
try:
    cb = resolve_codebase(codebase, root)
    tools = get_tools()
except CodebaseNotFoundError as e:
    console.print(f"error: {e}", style="red")
    raise typer.Exit(code=ExitCode.USER_ERROR)
except ToolNotFoundError as e:
    console.print(f"error: {e}", style="red")
    raise typer.Exit(code=ExitCode.ENV_ERROR)

# Nouveau: decorateur
@with_workspace
@handle_errors
def build(ctx: Context, codebase: str):
    cb = ctx.resolve_codebase(codebase)
    # ...
```

#### Pattern 2: Installation tool repete 9 fois

```python
# Actuel (~50 lignes par outil)
def setup_cmake(tools_dir: Path) -> bool:
    cmake_dir = tools_dir / "cmake"
    cmake_bin = cmake_dir / "bin" / ("cmake.exe" if is_windows() else "cmake")
    if cmake_bin.exists():
        log_ok("cmake (already installed)")
        return True
    version = get_github_latest_release("Kitware/CMake")
    # ... URL construction platform-specific ...
    download_and_extract(url, cmake_dir)
    # ... post-install platform-specific ...

# Nouveau: classe Tool (~20 lignes)
class CMakeTool(GitHubTool):
    spec = ToolSpec(id="cmake", ...)
    repo = "Kitware/CMake"
    def asset_name(...): ...
    def post_install(...): ...  # macOS .app bundle
```

#### Pattern 3: Console globale

```python
# Actuel
console = Console()  # Global

def check():
    console.print("...")  # Non testable

# Nouveau: injectable
class CheckerService:
    def __init__(self, console: ConsoleProtocol):
        self.console = console
```

### 2.3 Code a migrer tel quel (bon)

| Module | Raison |
|--------|--------|
| `platform.py` | Propre, testable, SRP |
| `build/native.py` | Bien decouope |
| `build/wasm.py` | Bien decoupe |
| `build/teensy.py` | Bien decoupe |
| `bridge.py` | Lifecycle propre |
| `codebase.py` | Simple, efficace |

---

## 3. Architecture cible

### 3.1 Structure des fichiers

```
ms/
├── __init__.py                 # __version__ only
├── __main__.py                 # main() -> cli.app:main
│
├── core/                       # LAYER 0: Domain (aucune dep externe)
│   ├── __init__.py
│   ├── result.py               # Result[T, E], Ok, Err ✅
│   ├── errors.py               # ErrorCode enum ✅
│   ├── workspace.py            # Workspace dataclass + detection ✅
│   ├── config.py               # Config typee (ports, paths, etc.) ✅
│   └── codebase.py             # Codebase resolution (Phase 3)
│
├── platform/                   # LAYER 1: Platform abstraction
│   ├── __init__.py
│   ├── detection.py            # Platform/Arch/LinuxDistro enums ✅
│   ├── paths.py                # home(), cache_dir(), etc. ✅
│   └── shell.py                # Shell env script generation (Phase 2.F)
│
├── output/                     # LAYER 1: Output abstraction
│   ├── __init__.py
│   └── console.py              # ConsoleProtocol + RichConsole ✅
│
├── tools/                      # LAYER 2: Tools infrastructure
│   ├── __init__.py             # Exports publics ✅
│   ├── base.py                 # ToolSpec, Tool ABC, Mode enum ✅
│   ├── http.py                 # HttpClient protocol + Real/Mock ✅
│   ├── api.py                  # Fonctions API: github, adoptium, zig, maven ✅
│   ├── github.py               # GitHubTool base class ✅
│   ├── state.py                # ToolState, load/save state.json ✅ (NOUVEAU)
│   ├── resolver.py             # ToolResolver - trouve binaires installes ✅
│   ├── download.py             # Downloader - HTTP + cache + progress ✅
│   ├── installer.py            # Installer - extract tar/zip, strip components ✅
│   ├── registry.py             # ToolRegistry - facade (Phase 2.F)
│   ├── wrapper.py              # WrapperGenerator - bash/cmd/ps1 (Phase 2.F)
│   │
│   └── definitions/            # Classes Tool (un fichier par outil)
│       ├── __init__.py         # ALL_TOOLS list, get_tool(id) (Phase 2.F)
│       ├── ninja.py            # NinjaTool(GitHubTool) ✅
│       ├── cmake.py            # CMakeTool(GitHubTool) (Phase 2.C)
│       ├── zig.py              # ZigTool(Tool) + wrappers (Phase 2.C)
│       ├── bun.py              # BunTool(GitHubTool) (Phase 2.C)
│       ├── uv.py               # UvTool(GitHubTool) (Phase 2.C)
│       ├── jdk.py              # JdkTool(Tool) - Adoptium API (Phase 2.D)
│       ├── maven.py            # MavenTool(Tool) - Maven Central (Phase 2.D)
│       ├── emscripten.py       # EmscriptenTool - git clone + emsdk (Phase 2.E)
│       ├── platformio.py       # PlatformioTool - script externe (Phase 2.E)
│       ├── cargo.py            # CargoTool(SystemTool) (Phase 2.E)
│       └── sdl2.py             # Sdl2Tool - Windows lib (Phase 2.E)
│
├── git/                        # LAYER 2: Git operations (Phase 3)
│   ├── __init__.py
│   ├── repository.py           # Repository class
│   └── multi.py                # Multi-repo operations
│
├── build/                      # LAYER 2: Build modules (Phase 4)
│   ├── __init__.py
│   ├── native.py               # SDL/CMake (migre tel quel)
│   ├── wasm.py                 # Emscripten (migre tel quel)
│   └── teensy.py               # PlatformIO (migre tel quel)
│
├── services/                   # LAYER 3: Application services (Phase 4)
│   ├── __init__.py
│   ├── checker.py              # CheckerService
│   ├── setup.py                # SetupService (bootstrap + bridge)
│   ├── builder.py              # BuildService
│   ├── updater.py              # UpdaterService
│   └── cleaner.py              # CleanerService
│
├── cli/                        # LAYER 4: Presentation (Phase 5)
│   ├── __init__.py
│   ├── app.py                  # Typer app + main()
│   ├── context.py              # CLIContext (DI container)
│   ├── decorators.py           # @with_workspace, @handle_errors
│   ├── interactive.py          # Mode interactif
│   └── commands/
│       └── ...
│
├── data/                       # Static data files
│   └── hints.toml              # Install hints par platform/distro
│
└── test/                       # Tests (415 actuellement)
    └── ...
```

### 3.2 Graphe de dependances

```
Layer 0 (Core)        Layer 1 (Platform)     Layer 2 (Infra)        Layer 3 (App)         Layer 4 (CLI)
──────────────        ──────────────────     ───────────────        ─────────────         ─────────────
                                                                                          
  result.py ────────► detection.py ────────► base.py ───────────► checker.py ─────────► commands/
      │                    │                     │                      │                     │
      │                    │                     ▼                      │                     │
  errors.py                │               github.py                    │                     │
      │                    │                     │                      │                     │
      ▼                    ▼                     ▼                      ▼                     ▼
  workspace.py ◄──── paths.py            resolver.py ──────────► setup.py ───────────► app.py
      │                    │                     │                      │                     │
      │                    │                     ▼                      │                     │
  config.py                │               download.py                  │                     │
      │                    │                     │                      │                     │
      ▼                    ▼                     ▼                      ▼                     │
  codebase.py         shell.py            installer.py ─────────► builder.py                 │
                           │                     │                      │                     │
                           │                     ▼                      │                     │
                      console.py           state.py                     │                     │
                                                 │                      ▼                     │
                                                 ▼                 updater.py                 │
                                           definitions/                 │                     │
                                                 │                      ▼                     │
                                                 └─────────────► cleaner.py                   │
                                                                        │                     │
                                           repository.py ◄──────────────┘                     │
                                                 │                                            │
                                                 ▼                                            │
                                             multi.py ◄───────────────────────────────────────┘
```

---

## 4. Plan d'execution detaille

### Phase 1: Foundation (4-5h) ✅ COMPLETE

**Objectif**: Briques de base sans dependances externes, 100% testables.

| Step | Fichier | Statut |
|------|---------|--------|
| 1.1 | `core/result.py` | ✅ |
| 1.2 | `core/errors.py` | ✅ |
| 1.3 | `platform/detection.py` | ✅ |
| 1.4 | `platform/paths.py` | ✅ |
| 1.5 | `output/console.py` | ✅ |
| 1.6 | `core/workspace.py` | ✅ |
| 1.7 | `core/config.py` | ✅ |
| 1.8 | Integration Phase 1 | ✅ |

**Livrable Phase 1**: ✅ 231 tests, 0 erreurs pyright

### Phase 2: Tools Infrastructure (8-10h) ✅ COMPLETE

**Objectif**: Systeme d'outils code-first, type-safe, testable.

**Resultat**: 717 tests, 0 erreurs pyright, 11 outils implementes

#### Etape 2.A: Foundation ✅ COMPLETE

| Step | Fichier | Statut | Notes |
|------|---------|--------|-------|
| 2.1 | `tools/base.py` | ✅ | **Simplifie**: 1 ABC au lieu de 3 protocols |
| 2.2 | `tools/http.py` | ✅ | |
| 2.3 | `tools/api.py` | ✅ | |
| 2.4 | `tools/github.py` | ✅ | **Modifie**: stateless, http passe a latest_version() |

#### Etape 2.B: Premier outil complet ✅ COMPLETE

| Step | Fichier | Statut | Notes |
|------|---------|--------|-------|
| 2.5 | `tools/definitions/ninja.py` | ✅ | Valide le design |
| 2.6 | `tools/download.py` | ✅ | **Simplifie**: sans download_to() |
| 2.7 | `tools/installer.py` | ✅ | |
| 2.8 | `tools/resolver.py` | ✅ | **Simplifie**: sans version, helpers supprimes |
| 2.9 | Integration 2.B | ✅ | test_integration.py |
| 2.9+ | `tools/state.py` | ✅ | **AJOUTE**: tracking versions installees |

#### Etape 2.C: Outils GitHub standard ✅ COMPLETE

| Step | Fichier | Statut | Notes |
|------|---------|--------|-------|
| 2.10 | `tools/definitions/cmake.py` | ✅ | GitHubTool + post_install macOS |
| 2.11 | `tools/definitions/zig.py` | ✅ | Tool - API custom ziglang.org |
| 2.12 | `tools/definitions/bun.py` | ✅ | **Tool** (pas GitHubTool) - tag format special |
| 2.13 | `tools/definitions/uv.py` | ✅ | GitHubTool |

#### Etape 2.D: Outils avec APIs custom ✅ COMPLETE

| Step | Fichier | Statut | Notes |
|------|---------|--------|-------|
| 2.14 | `tools/definitions/jdk.py` | ✅ | Tool - Adoptium API, JAVA_HOME env |
| 2.15 | `tools/definitions/maven.py` | ✅ | Tool - Maven Central XML |

#### Etape 2.E: Outils speciaux ✅ COMPLETE

| Step | Fichier | Statut | Notes |
|------|---------|--------|-------|
| 2.16 | `tools/definitions/emscripten.py` | ✅ | Tool - git clone + `get_install_commands()` |
| 2.17 | `tools/definitions/platformio.py` | ✅ | Tool - script + `get_install_commands()` |
| 2.18 | `tools/definitions/cargo.py` | ✅ | Tool (pas SystemTool) - system only |
| 2.19 | `tools/definitions/sdl2.py` | ✅ | GitHubTool - Windows only, lib |

#### Etape 2.F: Infrastructure finale ✅ COMPLETE

| Step | Fichier | Statut | Notes |
|------|---------|--------|-------|
| 2.20 | `tools/definitions/__init__.py` | ✅ | ALL_TOOLS, get_tool(), get_tools_by_mode() |
| 2.21 | `tools/registry.py` | ✅ | ToolRegistry facade |
| 2.22 | `tools/wrapper.py` | ✅ | WrapperGenerator - bash/cmd |
| 2.23 | `platform/shell.py` | ✅ | 4 fonctions + facade (bash/zsh/ps/cmd) |
| 2.24 | Integration Phase 2 | ✅ | test_integration_phase2.py |

**Livrable Phase 2**: ✅ COMPLETE
- ✅ 11 classes Tool implementees et testees
- ✅ `ToolRegistry` pour lister/filtrer les outils
- ✅ `Downloader` + `Installer` + `state.py` pour install/track
- ✅ `WrapperGenerator` pour creer les scripts
- ✅ Tests avec 100% mocked HTTP (717 tests)

**Commande de validation**:
```bash
uv run pytest ms/test/tools/ -v  # 486 passed
uv run pyright ms/tools/         # 0 errors
```

### Phase 3: Git & Codebase (2-3h) ✅ COMPLETE

**Objectif**: Operations git multi-repo propres et testables.

**Resultat**: 816 tests total (+99), 0 erreurs pyright

| Step | Fichier | Contenu | Status |
|------|---------|---------|--------|
| 3.1 | `git/repository.py` | `Repository` class, `GitStatus` dataclass, `status()`, `is_clean()`, `pull_ff()` | ✅ |
| 3.2 | `git/multi.py` | `find_repos()`, `status_all()`, `pull_all()` | ✅ |
| 3.3 | `core/codebase.py` | `Codebase` dataclass, `resolve()`, `list_all()` | ✅ |
| 3.4 | `data/hints.toml` | Install hints par platform/distro (150 lignes) | ✅ |
| 3.5 | Integration Phase 3 | Git status multi-repo (12 tests) | ✅ |

**Livrable Phase 3**: ✅ COMPLETE

**Commande de validation**:
```bash
uv run pytest ms/test/git/ ms/test/core/test_codebase.py -v  # 87 passed
uv run pyright ms/git/ ms/core/codebase.py                    # 0 errors
```

### Phase 4: Services (5-6h)

**Objectif**: Logique metier injectable, testable avec mocks.

**Decision 2025-01-25**: CheckerService decoupe en sous-checkers + migration directe ToolResolver.

| Step | Fichier | Contenu | Temps |
|------|---------|---------|-------|
| 4.1a | `services/checkers/workspace.py` | `WorkspaceChecker` - verifie open-control/, midi-studio/, config.toml | 30min |
| 4.1b | `services/checkers/tools.py` | `ToolsChecker` - verifie tools via ToolRegistry | 30min |
| 4.1c | `services/checkers/system.py` | `SystemChecker` - SDL2, ALSA, pkg-config | 30min |
| 4.1d | `services/checkers/runtime.py` | `RuntimeChecker` - virmidi, serial, MIDI | 30min |
| 4.1e | `services/checker.py` | `CheckerService` facade combinant les sous-checkers | 30min |
| 4.2 | `services/setup.py` | `SetupService` - bootstrap + build bridge/ext | 1h |
| 4.3 | `services/builder.py` | `BuildService` - dispatch native/wasm/teensy | 1h |
| 4.4 | `services/updater.py` | `UpdaterService` - git pull + tools upgrade | 1h |
| 4.5 | `services/cleaner.py` | `CleanerService` - clean artifacts | 30min |
| 4.6 | `build/*.py` | Migration native.py, wasm.py, teensy.py (utilise ToolRegistry direct) | 30min |
| 4.7 | Integration Phase 4 | Service complet avec DI | 30min |

**Livrable Phase 4**: Toute la logique metier fonctionne.

**Architecture CheckerService**:
```python
@dataclass
class CheckResult:
    name: str
    ok: bool
    message: str
    hint: str | None = None

class WorkspaceChecker:
    def check(self, workspace: Workspace) -> list[CheckResult]: ...

class ToolsChecker:
    def check(self, registry: ToolRegistry) -> list[CheckResult]: ...

class SystemChecker:
    def check(self, platform: Platform, hints: Hints) -> list[CheckResult]: ...

class RuntimeChecker:
    def check(self, platform: Platform, hints: Hints) -> list[CheckResult]: ...

class CheckerService:
    def __init__(self, workspace: WorkspaceChecker, tools: ToolsChecker, ...): ...
    def check_all(self) -> list[CheckResult]: ...
```

### Phase 5: CLI Layer (4-5h)

**Objectif**: Commandes thin wrappers, CLI complete mode dev.

| Step | Fichier | Contenu | Temps |
|------|---------|---------|-------|
| 5.1 | `cli/context.py` | `CLIContext` (DI container) | 30min |
| 5.2 | `cli/decorators.py` | `@with_workspace`, `@handle_errors` | 30min |
| 5.3 | `cli/app.py` | Typer app, `--version` | 30min |
| 5.4-5.12 | `cli/commands/*.py` | Toutes les commandes | 2.5h |
| 5.13 | `cli/interactive.py` | Mode interactif (menu) | 30min |
| 5.14 | Integration Phase 5 | Test E2E complet | 30min |

**Livrable Phase 5**: CLI complete, ms_cli/ peut etre supprime.

### Phase 6: End-User Mode & Cleanup (3-4h)

**Objectif**: Mode end-user, migration finale.

| Step | Fichier | Contenu | Temps |
|------|---------|---------|-------|
| 6.1 | Distribution | Fetch binaires GitHub Releases | 1h |
| 6.2 | Firmware selector | Selection firmware + teensy.exe | 30min |
| 6.3 | Setup wizard | Flow simplifie end-user | 30min |
| 6.4 | pyproject.toml | Nouveau entry point `ms` | 15min |
| 6.5 | Supprimer ms_cli/ | Ancien code | 15min |
| 6.6 | Supprimer setup.sh | Legacy bash | 5min |
| 6.7 | setup-minimal.sh | Pointer vers `ms` | 15min |
| 6.8 | Documentation | README, CHANGELOG | 30min |

**Livrable Phase 6**: Migration complete.

---

## 5. Specifications techniques

### 5.1 Tools Architecture (Code-first simplifie)

> **Note**: Architecture simplifiee le 2025-01-25. 
> 1 ABC `Tool` au lieu de 3 protocols. Outils stateless.

#### 5.1.1 Classe de base (`tools/base.py`)

```python
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum, auto
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ms.core.result import Result
    from ms.platform.detection import Arch, Platform
    from ms.tools.http import HttpClient, HttpError


class Mode(Enum):
    """Installation mode."""
    DEV = auto()
    ENDUSER = auto()


@dataclass(frozen=True, slots=True)
class ToolSpec:
    """Immutable tool metadata."""
    id: str
    name: str
    required_for: frozenset[Mode]
    version_args: tuple[str, ...] = ("--version",)


class Tool(ABC):
    """Abstract base class for all tools.
    
    Subclasses must define:
    - spec: ToolSpec with metadata
    - latest_version(): Fetch latest version
    - download_url(): Get download URL
    
    Most methods have sensible defaults.
    """
    
    spec: ToolSpec
    
    @abstractmethod
    def latest_version(self, http: HttpClient) -> Result[str, HttpError]:
        """Fetch latest version from source."""
        ...
    
    @abstractmethod
    def download_url(self, version: str, platform: Platform, arch: Arch) -> str:
        """Get download URL for version/platform."""
        ...
    
    def install_dir_name(self) -> str:
        """Directory name under tools/. Default: spec.id"""
        return self.spec.id
    
    def strip_components(self) -> int:
        """Path components to strip when extracting. Default: 0"""
        return 0
    
    def bin_path(self, tools_dir: Path, platform: Platform) -> Path | None:
        """Path to main binary. Default: tools_dir/{id}/{id}[.exe]"""
        return tools_dir / self.spec.id / platform.exe_name(self.spec.id)
    
    def is_installed(self, tools_dir: Path, platform: Platform) -> bool:
        """Check if tool is installed."""
        path = self.bin_path(tools_dir, platform)
        return path is not None and path.exists()
    
    def post_install(self, install_dir: Path, platform: Platform) -> None:
        """Post-installation actions. Default: no-op"""
        pass
```

#### 5.1.2 SystemTool pour outils system-only

```python
class SystemTool(Tool):
    """Base for tools that must be installed by user (cargo, etc.)."""
    
    install_hint: str  # URL or command to install
    
    def latest_version(self, http: HttpClient) -> Result[str, HttpError]:
        """System tools don't have downloadable versions."""
        return Err(HttpError(url="", status=0, message="System tool - install manually"))
    
    def download_url(self, version: str, platform: Platform, arch: Arch) -> str:
        raise NotImplementedError(f"System tool - install with: {self.install_hint}")
```

#### 5.1.3 GitHubTool pour outils GitHub Releases

```python
class GitHubTool(Tool):
    """Base class for tools distributed via GitHub Releases.
    
    Subclasses must define:
    - spec: ToolSpec
    - repo: GitHub repository (e.g., "ninja-build/ninja")
    - asset_name(): Return asset filename for platform/arch
    """
    
    spec: ToolSpec
    repo: str
    
    def latest_version(self, http: HttpClient) -> Result[str, HttpError]:
        """Fetch latest release version from GitHub."""
        return github_latest_release(http, self.repo)
    
    def download_url(self, version: str, platform: Platform, arch: Arch) -> str:
        asset = self.asset_name(version, platform, arch)
        return f"https://github.com/{self.repo}/releases/download/v{version}/{asset}"
    
    @abstractmethod
    def asset_name(self, version: str, platform: Platform, arch: Arch) -> str:
        """Return asset filename for platform."""
        ...
    
    def post_install(self, install_dir: Path, platform: Platform) -> None:
        """Make binary executable on Unix."""
        if platform.is_unix:
            bin_path = install_dir / platform.exe_name(self.spec.id)
            if bin_path.exists():
                bin_path.chmod(0o755)
```

#### 5.1.4 Exemple: NinjaTool

```python
class NinjaTool(GitHubTool):
    """Ninja build system - simplest GitHub tool."""
    
    spec = ToolSpec(
        id="ninja",
        name="Ninja",
        required_for=frozenset({Mode.DEV}),
    )
    repo = "ninja-build/ninja"
    
    def asset_name(self, version: str, platform: Platform, arch: Arch) -> str:
        match platform:
            case Platform.LINUX:
                suffix = "-aarch64" if arch == Arch.ARM64 else ""
                return f"ninja-linux{suffix}.zip"
            case Platform.MACOS:
                return "ninja-mac.zip"
            case Platform.WINDOWS:
                return "ninja-win.zip"
```

#### 5.1.5 State tracking (`tools/state.py`)

```python
@dataclass(frozen=True, slots=True)
class ToolState:
    """State of an installed tool."""
    version: str
    installed_at: str
    
    @classmethod
    def now(cls, version: str) -> ToolState:
        return cls(version=version, installed_at=datetime.now().isoformat())


def load_state(tools_dir: Path) -> dict[str, ToolState]:
    """Load tool state from tools/state.json."""
    ...

def save_state(tools_dir: Path, state: dict[str, ToolState]) -> None:
    """Save tool state to tools/state.json."""
    ...

def get_installed_version(tools_dir: Path, tool_id: str) -> str | None:
    """Get installed version for a tool."""
    ...

def set_installed_version(tools_dir: Path, tool_id: str, version: str) -> None:
    """Set installed version for a tool."""
    ...
```

#### 5.1.6 Liste des outils ✅ TOUS IMPLEMENTES

| ID | Classe | Base | Source | Tests | Notes |
|----|--------|------|--------|-------|-------|
| ninja | `NinjaTool` | `GitHubTool` | ninja-build/ninja | 22 | ✅ |
| cmake | `CMakeTool` | `GitHubTool` | Kitware/CMake | 20 | ✅ post_install macOS |
| zig | `ZigTool` | `Tool` | ziglang.org | 17 | ✅ API custom |
| bun | `BunTool` | `Tool` | oven-sh/bun | 18 | ✅ **Deviation**: Tool pas GitHubTool |
| uv | `UvTool` | `GitHubTool` | astral-sh/uv | 18 | ✅ |
| jdk | `JdkTool` | `Tool` | api.adoptium.net | 22 | ✅ JAVA_HOME env |
| maven | `MavenTool` | `Tool` | repo1.maven.org | 19 | ✅ XML parsing |
| emscripten | `EmscriptenTool` | `Tool` | git clone | 25 | ✅ get_install_commands() |
| platformio | `PlatformioTool` | `Tool` | get-platformio.py | 19 | ✅ get_install_commands() |
| cargo | `CargoTool` | `Tool` | System PATH | 13 | ✅ **Deviation**: pas SystemTool |
| sdl2 | `Sdl2Tool` | `GitHubTool` | libsdl-org/SDL | 20 | ✅ Windows only |
| **TOTAL** | | | | **213** | |

### 5.2 Config typee

```python
# ms/core/config.py (deja implemente)

@dataclass(frozen=True)
class PortsConfig:
    hardware: int = 9000
    native: int = 9001
    wasm: int = 9002
    
@dataclass(frozen=True)
class ControllerPortsConfig:
    core_native: int = 8000
    core_wasm: int = 8100
    bitwig_native: int = 8001
    bitwig_wasm: int = 8101

@dataclass(frozen=True)
class MidiConfig:
    linux: str = "VirMIDI"
    macos_input: str = "MIDI Studio IN"
    macos_output: str = "MIDI Studio OUT"
    windows: str = "loopMIDI"

@dataclass(frozen=True)
class PathsConfig:
    bridge: str = "open-control/bridge"
    extension: str = "midi-studio/plugin-bitwig/host"
    tools: str = "tools"

@dataclass(frozen=True)
class Config:
    ports: PortsConfig
    controller_ports: ControllerPortsConfig
    midi: MidiConfig
    paths: PathsConfig
    raw: dict[str, Any]
```

### 5.3 pyproject.toml

```toml
[project]
name = "ms"
version = "0.2.0"
description = "MIDI Studio CLI"
requires-python = ">=3.13"
dependencies = [
    "rich>=13.0.0",
    "typer>=0.12.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0.0",
    "pytest-mock>=3.12.0",
    "pyright>=1.1.350",
]

[project.scripts]
ms = "ms.cli.app:main"

[tool.pytest.ini_options]
testpaths = ["ms/test"]
python_files = ["test_*.py"]
python_functions = ["test_*"]
addopts = "-v --tb=short"

[tool.pyright]
include = ["ms"]
exclude = ["ms_cli", "ms/test"]
pythonVersion = "3.13"
typeCheckingMode = "strict"

[tool.ruff]
line-length = 100
target-version = "py313"

[tool.ruff.lint]
select = ["E", "F", "I", "UP", "B", "SIM"]
```

---

## 6. Questions restantes

### 6.1 Resolues avec Simon (2025-01-24)

| # | Question | Reponse |
|---|----------|---------|
| Q1 | **CI GitHub Actions**: Tu as deja une CI? | **Oui** - Tests multi-OS possibles |
| Q2 | **Pyright strict**: On part sur strict des le debut? | **Oui strict** - Qualite maximale |
| Q3 | **Premiere commande a tester**: Apres Phase 4? | **Oui `ms check`** - Validation logique |

### 6.2 Points techniques resolus

| # | Point | Phase | Resolution |
|---|-------|-------|------------|
| T1 | Format exact des wrappers PowerShell | Phase 2 | ✅ Implemente dans `platform/shell.py` |
| T2 | Adoptium API pour JDK 25 (EA?) | Phase 2 | ✅ JDK 21 par defaut, configurable |
| T3 | Cache local: ou stocker? | Phase 2 | ✅ `workspace/.cache/downloads/` |
| T4 | Emscripten: git clone vs archive? | Phase 2 | ✅ Git clone + `get_install_commands()` |
| T5 | PlatformIO: garder install globale? | Phase 2 | ✅ Oui (~/.platformio) via `get_install_commands()` |
| T6 | Version tracking | Phase 2 | ✅ `tools/state.json` via state.py |
| T7 | BunTool tag format | Phase 2 | ✅ Tool direct (pas GitHubTool) pour `bun-v1.x.x` |
| T8 | SystemTool abstraction | Phase 2 | ✅ YAGNI - inline dans CargoTool |

---

## 7. Risques et mitigations

| Risque | Probabilite | Impact | Mitigation | Status |
|--------|-------------|--------|------------|--------|
| ~~Tools.toml trop complexe~~ | - | - | Architecture code-first | ✅ ELIMINE |
| ~~Protocols trop abstraits~~ | - | - | Simplifie a 1 ABC | ✅ ELIMINE |
| ~~Downloads flaky~~ | - | - | Mock HTTP partout | ✅ RESOLU (717 tests mocked) |
| ~~Dependance circulaire~~ | - | - | Graphe deps strict | ✅ RESOLU (pyright 0 errors) |
| ~~JDK 25 pas dispo~~ | - | - | Fallback JDK 21 LTS | ✅ RESOLU (JDK 21 par defaut) |
| **Platform-specific bugs** | Haute | Moyen | CI multi-OS, tester Windows tot | En cours |
| **Migration incomplete** | Faible | Haut | Cohabitation ms_cli/ et ms/ jusqu'a 100% | En cours |
| **Regression fonctionnelle** | Moyenne | Haut | Tests E2E sur workspace reel en fin de phase | A faire Phase 6 |

---

## Annexe: Checklist de validation

### Avant chaque step

- [ ] Le step precedent est complete et teste
- [ ] Les dependances sont definies
- [ ] Le test est ecrit (ou au moins sketche)

### Apres chaque step

- [ ] Tests passent: `pytest ms/test/<module>/ -v`
- [ ] Pas d'import circulaire: `python -c "from ms.<module> import *"`
- [ ] Type check: `pyright ms/<module>/`
- [ ] Docstrings sur fonctions publiques

### En fin de phase

- [ ] Integration test passe
- [ ] Pas de regression
- [ ] Documentation a jour

---

## 8. Etat actuel

### Phase 1: COMPLETE ✅

**231 tests passent, 0 erreurs pyright**

```
ms/
├── __init__.py                     # __version__ = "0.2.0"
├── core/
│   ├── result.py                   # Result[T,E] monad (Ok/Err)
│   ├── errors.py                   # ErrorCode enum (0-5)
│   ├── workspace.py                # Workspace dataclass + detection
│   └── config.py                   # Typed config
├── platform/
│   ├── detection.py                # Platform/Arch/LinuxDistro enums
│   └── paths.py                    # home(), user_config_dir()
├── output/
│   └── console.py                  # ConsoleProtocol + Mock/Rich impl
└── test/                           # 231 tests
```

### Phase 2: COMPLETE ✅

**717 tests total (486 tools), 0 erreurs pyright**

#### Structure finale

```
ms/tools/
├── __init__.py          # 56 lignes - exports publics
├── base.py              # 169 lignes - Mode, ToolSpec, Tool ABC
├── http.py              # 306 lignes - HttpClient + Real/Mock
├── api.py               # 238 lignes - github, adoptium, zig, maven APIs
├── github.py            # 104 lignes - GitHubTool base class
├── state.py             # 100 lignes - ToolState, load/save
├── download.py          # 176 lignes - Downloader avec cache
├── installer.py         # 238 lignes - Extract tar/zip
├── resolver.py          # 141 lignes - ToolResolver
├── registry.py          # 295 lignes - ToolRegistry facade
├── wrapper.py           # 218 lignes - WrapperGenerator bash/cmd
└── definitions/
    ├── __init__.py      # 111 lignes - ALL_TOOLS, get_tool()
    ├── ninja.py         # 57 lignes
    ├── cmake.py         # 101 lignes
    ├── zig.py           # 117 lignes
    ├── bun.py           # 99 lignes
    ├── uv.py            # 86 lignes
    ├── jdk.py           # 138 lignes
    ├── maven.py         # 85 lignes
    ├── emscripten.py    # 155 lignes
    ├── platformio.py    # 132 lignes
    ├── cargo.py         # 95 lignes
    └── sdl2.py          # 122 lignes

ms/platform/
├── detection.py         # Platform/Arch/LinuxDistro
├── paths.py             # home(), user_config_dir()
└── shell.py             # 259 lignes - activation scripts (NOUVEAU)
```

#### Progression detaillee

| Etape | Steps | Status | Tests |
|-------|-------|--------|-------|
| 2.A Foundation | 2.1-2.4 | ✅ COMPLETE | ~80 |
| 2.B Premier outil | 2.5-2.9+ | ✅ COMPLETE | ~104 |
| 2.C Outils GitHub | 2.10-2.13 | ✅ COMPLETE | ~73 |
| 2.D APIs custom | 2.14-2.15 | ✅ COMPLETE | ~41 |
| 2.E Outils speciaux | 2.16-2.19 | ✅ COMPLETE | ~77 |
| 2.F Infra finale | 2.20-2.24 | ✅ COMPLETE | ~111 |

#### Metriques finales Phase 2

| Metrique | Valeur |
|----------|--------|
| Fichiers tools/ | 23 |
| Lignes de code | ~3600 |
| Tests tools | 486 |
| Tests totaux | 717 |
| Pyright errors | 0 |
| Outils implementes | 11/11 |
| Conformite plan | ~95% |

### Prochaine phase: Phase 3 (Git & Codebase)

| Step | Fichier | Contenu |
|------|---------|---------|
| 3.1 | `git/repository.py` | Repository class, status(), pull_ff() |
| 3.2 | `git/multi.py` | find_repos(), status_all() |
| 3.3 | `core/codebase.py` | Codebase dataclass |
| 3.4 | `data/hints.toml` | Install hints |
| 3.5 | Integration | Git status multi-repo |

**Livrable Phase 3**: `ms status` fonctionnel

---

*Document mis a jour: 2025-01-25 - Phase 2 COMPLETE*
