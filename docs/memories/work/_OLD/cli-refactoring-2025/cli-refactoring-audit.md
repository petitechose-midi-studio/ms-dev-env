# CLI Refactoring - Audit & Decisions

> **Date de création**: 2025-01-24
> **Statut**: Phase 0 - Clarifications en cours
> **Participants**: Simon (owner), Claude (assistant)

---

## Table des matières

1. [Contexte du projet](#1-contexte-du-projet)
2. [Objectifs](#2-objectifs)
3. [Audit de l'existant](#3-audit-de-lexistant)
4. [Décisions prises](#4-décisions-prises)
5. [Questions ouvertes](#5-questions-ouvertes)
6. [Plan de travail](#6-plan-de-travail)
7. [Architecture cible](#7-architecture-cible)
8. [Historique des échanges](#8-historique-des-échanges)

---

## 1. Contexte du projet

### 1.1 Description

**MIDI Studio** est un projet hardware/software de contrôleur MIDI professionnel. Le workspace est un monorepo qui orchestre plusieurs repositories git:

```
pc/                          # Workspace root (ce repo)
├── ms_cli/                  # CLI Python (orchestration) - À REFACTORER
├── midi-studio/             # Produit principal (repos clonés)
│   ├── core/                # Firmware standalone (Teensy)
│   ├── plugin-bitwig/       # Firmware + extension DAW
│   └── hardware/            # PCB KiCad, CNC, 3D
├── open-control/            # Framework embarqué (repos clonés)
│   ├── framework/           # HAL + state management
│   ├── bridge/              # Serial-to-UDP (Rust)
│   ├── hal-teensy/          # Implémentation Teensy
│   ├── ui-lvgl/             # Intégration LVGL
│   └── ...
└── tools/                   # Toolchains bundled (gitignored)
```

### 1.2 Stack technique

| Couche | Technologies |
|--------|-------------|
| **CLI** | Python 3.13, Typer, Rich |
| **Firmware** | C++17, PlatformIO, Teensy 4.1 (ARM Cortex-M7 @ 450MHz) |
| **UI embarquée** | LVGL (Light & Versatile Graphics Library) |
| **Bridge** | Rust (tokio, ratatui TUI, serialport) |
| **Simulateur** | SDL2, Zig toolchain, Emscripten (WASM) |
| **Extension Bitwig** | Java (Maven, JDK 21+) |
| **Build** | CMake, Ninja, Zig (cross-compilation) |

### 1.3 Deux modes d'installation

1. **End-user**: Récupère uniquement les binaires finaux (bridge, extension Bitwig, firmware)
2. **Developer**: Setup complet avec tous les outils de build

---

## 2. Objectifs

### 2.1 Objectifs exprimés par Simon

> "Je veux un code parfait pour les scripts de setup et toute la CLI, claire simple, bien organisée, robuste performante, et surtout : maintenable, qui respecte les principes SOLID"

> "Je suis pas pressé, je veux faire les choses bien, dans le bon ordre, si pertinent de repartir from scratch c'est envisageable"

### 2.2 Objectifs techniques

- **Maintenabilité**: Ajouter un outil/feature sans toucher au code existant
- **Testabilité**: Chaque composant testable en isolation
- **DX (Developer Experience)**: CLI intuitive, messages d'erreur clairs
- **Zero-config**: L'installer doit "just work" pour dev et end-user
- **SOLID**: Respect strict des principes

---

## 3. Audit de l'existant

### 3.1 Métriques globales

| Fichier | Lignes | Responsabilités | Violations SOLID |
|---------|--------|-----------------|------------------|
| `cli.py` | 1569 | ~15 | SRP, OCP, DIP |
| `setup_bootstrap.py` | 1081 | ~8 | SRP, OCP |
| `tools.py` | 299 | 3 | OCP, DIP |
| `teensy.py` | 169 | 1 | - |
| `errors.py` | 151 | 2 | - |
| `wasm.py` | 136 | 1 | - |
| `native.py` | 134 | 1 | - |
| `bridge.py` | 131 | 2 | - |
| `codebase.py` | 77 | 1 | - |
| `platform.py` | 75 | 1 | - |
| `config.py` | 17 | 1 | SRP (trop simple) |
| **Total** | **3854** | | |

### 3.2 Problèmes majeurs identifiés

#### 3.2.1 `cli.py` - God Module (1569 lignes)

**15+ responsabilités mélangées:**
1. Routing Typer (définitions de commandes)
2. Workspace detection
3. Git operations (parse, status, pull)
4. Console output helpers
5. Tool checking
6. Environment validation (commande `check`)
7. Setup orchestration (commande `setup`)
8. Update logic (commande `update`)
9. Clean logic (commande `clean`)
10. Build dispatching
11. Upload/Monitor
12. Interactive menu
13. Alias handling
14. Shell completion
15. Bridge launching

**God Functions:**
- `check()` : 260 lignes
- `setup()` : 160 lignes
- `update()` : 185 lignes

**Duplication - Pattern try/except répété 8 fois:**
```python
try:
    cb = resolve_codebase(codebase, root)
    tools = get_tools()
except CodebaseNotFoundError as e:
    console.print(f"error: {e}", style="red")
    raise typer.Exit(code=ExitCode.USER_ERROR)
except ToolNotFoundError as e:
    console.print(f"error: {e}", style="red")
    raise typer.Exit(code=ExitCode.ENV_ERROR)
```

#### 3.2.2 `setup_bootstrap.py` - Monolithe (1081 lignes)

**8 responsabilités:**
1. Download utilities
2. GitHub API
3. Architecture detection
4. 9 installateurs différents (cmake, ninja, zig, bun, jdk, maven, sdl2, emscripten, platformio)
5. System deps checking
6. Shell configuration
7. Wrapper generation
8. Installation verification

**Duplication massive**: Pattern d'installation répété 9 fois (~300 lignes dupliquées)

#### 3.2.3 `tools.py` - Violation OCP

**18 méthodes** pour 18 outils. Ajouter un outil = modifier la classe:
```python
class ToolResolver:
    def cmake(self) -> Path: ...
    def ninja(self) -> Path: ...
    def pio(self) -> Path: ...
    # ... 15 autres méthodes
```

#### 3.2.4 `config.py` - Trop simple

```python
@dataclass(frozen=True)
class Config:
    raw: dict[str, Any]  # Accès non typé partout
```

### 3.3 Violations SOLID détaillées

#### SRP (Single Responsibility)
- `cli.py`: 15+ responsabilités (max recommandé: 1-2)
- `setup_bootstrap.py`: 8 responsabilités

#### OCP (Open/Closed)
- `ToolResolver`: Ajouter un outil = modifier la classe
- `setup_bootstrap.py`: Ajouter un installateur = modifier le fichier

#### DIP (Dependency Inversion)
- `console = Console()` : Global, non injectable
- `tools = ToolResolver(workspace_root())` : Créé inline

### 3.4 Dette technique

| Pattern dupliqué | Occurrences | Lignes |
|------------------|-------------|--------|
| Try/except codebase+tools | 8 | ~80 |
| Tool installer pattern | 9 | ~300 |
| Wrapper generation | 4 | ~100 |
| Platform-specific URL | 9 | ~150 |

**Total estimé**: ~630 lignes de duplication (16% du code)

### 3.5 Points positifs

- `platform.py` : Clean, testable, single responsibility - **modèle à suivre**
- `build/*.py` : Bien découpés, fonctions pures
- `bridge.py` : Bien structuré avec lifecycle propre
- Type hints présents partout
- Docstrings présentes

---

## 4. Décisions prises

### 4.1 Approche générale

| Décision | Choix | Raison |
|----------|-------|--------|
| Refactoring vs From scratch | **From scratch** | 16% duplication, violations majeures, design intentionnel souhaité |
| Tests | **En parallèle** | Écrire le test avant de considérer une fonction "terminée" |
| Backward compatibility | **Non** | "Pas de backward, que du propre" |

### 4.2 Configuration externe pour tools

| Aspect | Sans config | Avec config |
|--------|-------------|-------------|
| Ajouter un outil | 67 lignes, 4 fichiers | 10 lignes, 1 fichier |
| Risque de régression | Élevé (code) | Faible (data) |
| Testable | Difficile | Trivial |

**Décision**: Utiliser `tools.toml` pour la définition des outils.

---

## 5. Questions ouvertes

### Q1: Scope des commandes

| Commande | Usage actuel | Recommandation | **Réponse Simon** |
|----------|--------------|----------------|-------------------|
| `ms check` | Fréquent | ✅ Garder | |
| `ms setup [--bootstrap]` | Fréquent | ✅ Garder | |
| `ms build <cb> [target]` | Fréquent | ✅ Garder | |
| `ms run <cb>` | Fréquent | ✅ Garder | |
| `ms web <cb>` | Fréquent | ✅ Garder | |
| `ms upload <cb>` | Fréquent | ✅ Garder | |
| `ms monitor <cb>` | Fréquent | ✅ Garder | |
| `ms clean [cb]` | Occasionnel | ✅ Garder | |
| `ms update` | Occasionnel | ✅ Garder | |
| `ms status/changes` | Occasionnel | ⚠️ Garder? | |
| `ms bridge` | Fréquent | ✅ Garder | |
| `ms core` | Alias | ❓ Utile? | |
| `ms bitwig` | Alias | ❓ Utile? | |
| `ms icons` | Rare | ⚠️ Garder? | |
| `ms completion` | Rare | ✅ Simplifier | |
| `ms r/w/b` (aliases) | ? | ❓ Utilisés? | |
| Mode interactif | ? | ❓ Utilisé? | |

### Q2: End-user binaries

D'où viennent les binaires pour l'end-user?

| Option | Description | Recommandation |
|--------|-------------|----------------|
| A | GitHub Releases | ✅ Recommandé |
| B | Build local | |
| C | CDN hosted | |

**Quels binaires?**
- [ ] `oc-bridge` (Linux/macOS/Windows)
- [ ] `midi_studio.bwextension`
- [ ] Firmware `.hex`/`.uf2`

**Réponse Simon**: _À compléter_

### Q3: Versioning strategy

| Option | Description | Recommandation |
|--------|-------------|----------------|
| A | Latest always | ✅ Recommandé |
| B | Pinned + update | |
| C | Range (>=x.y) | |

**Réponse Simon**: _À compléter_

### Q4: Shell configuration

| Option | Description | Recommandation |
|--------|-------------|----------------|
| A | Modifier .bashrc/.zshrc | Actuel, invasif |
| B | Script d'activation | ✅ Recommandé |
| C | Wrapper auto-source | |

**Réponse Simon**: _À compléter_

### Q5: Nom du package

| Option | Avantage | Inconvénient |
|--------|----------|--------------|
| `ms_cli` | Actuel | Underscore |
| `ms` | Simple | Peut confliter |
| `midi_studio_cli` | Explicite | Long |
| `mscli` | Court | Moins lisible |

**Recommandation**: `ms`

**Réponse Simon**: _À compléter_

### Q6: Structure des repos clonés

Structure actuelle:
```
workspace/
├── open-control/     # N repos
├── midi-studio/      # N repos
```

**Réponse Simon**: _Garder? Changer?_

### Q7: Offline mode

| Option | Description |
|--------|-------------|
| A | Internet requis | ✅ Recommandé v1 |
| B | Cache local | Pour plus tard |
| C | Bundle complet | |

**Réponse Simon**: _À compléter_

### Q8: Logging/Verbosity

```bash
ms setup              # Normal
ms setup -v           # Verbose
ms setup -vv          # Debug
ms setup -q           # Quiet
```

**Réponse Simon**: _À compléter_

---

## 6. Plan de travail

### Vue d'ensemble

```
Phase 0: Clarifications     [EN COURS]
    ↓
Phase 1: Foundation         ~4h
    ↓
Phase 2: Tools Infra        ~6h
    ↓
Phase 3: Services           ~5h
    ↓
Phase 4: CLI Layer          ~4h
    ↓
Phase 5: End-User Mode      ~3h
    ↓
Phase 6: Finalization       ~3h

Total estimé: ~25h
```

### Phase 0: Clarifications
- [ ] Répondre aux 8 questions
- [ ] Valider l'architecture finale
- [ ] Définir les interfaces clés

### Phase 1: Foundation (~4h)
- [ ] `Result[T]` type
- [ ] Platform detection (enum-based)
- [ ] Console abstraction (injectable)
- [ ] Workspace detection
- [ ] Config loading (typed, validated)
- [ ] Tests unitaires

### Phase 2: Tools Infrastructure (~6h)
- [ ] `tools.toml` schema + parser
- [ ] Tool registry (data-driven)
- [ ] Tool resolver (uses registry)
- [ ] Generic installer (download, extract, verify)
- [ ] Wrapper generator
- [ ] Tests

### Phase 3: Services Layer (~5h)
- [ ] `CheckerService`
- [ ] `SetupService`
- [ ] `BuildService`
- [ ] `UpdateService`
- [ ] Tests d'intégration

### Phase 4: CLI Layer (~4h)
- [ ] Typer app setup
- [ ] Commands (thin wrappers)
- [ ] Error handling
- [ ] Tests CLI

### Phase 5: End-User Mode (~3h)
- [ ] Binary distribution logic
- [ ] Simplified setup flow
- [ ] Version checking
- [ ] Tests E2E

### Phase 6: Finalization (~3h)
- [ ] Migration
- [ ] Documentation
- [ ] CI/CD
- [ ] Cleanup ancien code

---

## 7. Architecture cible

### 7.1 Structure proposée

```
ms/
├── __init__.py              # Version only
├── __main__.py              # Entry point only
│
├── cli/                     # Layer: Presentation
│   ├── __init__.py
│   ├── app.py               # Typer app creation
│   ├── context.py           # CLI context
│   ├── decorators.py        # @with_workspace, @handle_errors
│   └── commands/
│       ├── __init__.py
│       ├── check.py
│       ├── setup.py
│       ├── build.py
│       ├── upload.py
│       ├── status.py
│       ├── update.py
│       ├── clean.py
│       └── bridge.py
│
├── core/                    # Layer: Domain
│   ├── __init__.py
│   ├── workspace.py
│   ├── codebase.py
│   ├── config.py
│   └── result.py
│
├── services/                # Layer: Application
│   ├── __init__.py
│   ├── checker.py
│   ├── builder.py
│   ├── updater.py
│   └── cleaner.py
│
├── tools/                   # Layer: Infrastructure
│   ├── __init__.py
│   ├── registry.py
│   ├── resolver.py
│   ├── runner.py
│   └── installer/
│       ├── __init__.py
│       ├── base.py
│       ├── archive.py
│       └── providers/
│           ├── github.py
│           ├── adoptium.py
│           ├── maven.py
│           └── emsdk.py
│
├── git/                     # Layer: Infrastructure
│   ├── __init__.py
│   ├── repository.py
│   └── status.py
│
├── platform/                # Layer: Infrastructure
│   ├── __init__.py
│   ├── detection.py
│   ├── paths.py
│   └── shell.py
│
├── output/                  # Layer: Infrastructure
│   ├── __init__.py
│   ├── console.py
│   └── progress.py
│
└── data/                    # Static data
    ├── tools.toml
    └── hints.toml
```

### 7.2 Patterns clés

#### Result Type
```python
@dataclass
class Success(Generic[T]):
    value: T

@dataclass
class Failure:
    error: str
    code: ErrorCode

Result = Success[T] | Failure
```

#### Tool Registry (Data-Driven)
```toml
# tools.toml
[cmake]
repo = "Kitware/CMake"
bundled_paths = ["cmake/bin/cmake"]
version_args = ["--version"]
required_for = ["developer"]

[cmake.platforms]
linux = "cmake-{version}-linux-{arch}.tar.gz"
macos = "cmake-{version}-macos-universal.tar.gz"
windows = "cmake-{version}-windows-x86_64.zip"
```

#### Protocol-based DI
```python
class ConsoleProtocol(Protocol):
    def print(self, msg: str, style: str = "") -> None: ...
    def error(self, msg: str) -> None: ...

class CheckerService:
    def __init__(self, console: ConsoleProtocol, tools: ToolResolver):
        self.console = console
        self.tools = tools
```

---

## 8. Historique des échanges

### 2025-01-24 - Session initiale

**Simon**: Demande analyse complète de la codebase

**Claude**: 
- Exploration de la structure (midi-studio, open-control, ms_cli, tools)
- Identification du stack technique
- Première vue d'ensemble

**Simon**: "pas de delegation tu fais le travail toi meme"

**Claude**: Analyse directe sans agents

**Simon**: "je suis en train de construire l'installeur / cli pour gerer ca [...] je veux un code parfait [...] maintenable, qui respecte les principes solid"

**Claude**: 
- Identification des problèmes majeurs
- Proposition d'architecture SOLID
- Questions initiales

**Simon**: 
1. "je veux deja une analyse exhaustive et fine de l'existant"
2. "il faudra le faire [tests], on peut envisager du tdd"
3. "pas de backward, que du propre"
4. "qu'en penses tu [config externe], je veux le plus propre et maintenable"
5. "oui [end-user vs dev], on tracke les binaires finaux"

**Claude**: Audit complet de 3854 lignes de code
- Métriques détaillées
- Violations SOLID identifiées
- Dette technique quantifiée
- Plan en 6 phases proposé
- 8 questions de clarification

**Simon**: "deja inscris toutes tes questions et l'historique de la conversation, les decisions prises tout ca dans une memoire"

**Claude**: Création de ce document

---

## Annexes

### A. Fichiers analysés

```
ms_cli/__init__.py          (3 lignes)
ms_cli/__main__.py          (11 lignes)
ms_cli/bridge.py            (131 lignes)
ms_cli/cli.py               (1569 lignes)
ms_cli/codebase.py          (77 lignes)
ms_cli/config.py            (17 lignes)
ms_cli/errors.py            (151 lignes)
ms_cli/platform.py          (75 lignes)
ms_cli/setup_bootstrap.py   (1081 lignes)
ms_cli/tools.py             (299 lignes)
ms_cli/build/__init__.py    (1 ligne)
ms_cli/build/native.py      (134 lignes)
ms_cli/build/teensy.py      (169 lignes)
ms_cli/build/wasm.py        (136 lignes)
```

### B. Commandes CLI actuelles

```bash
ms                    # Mode interactif
ms --version          # Version
ms check              # Vérifie l'environnement
ms setup              # Build bridge + extension
ms setup --bootstrap  # Installation complète des tools
ms build <cb> [target]  # Build (teensy|native|wasm)
ms run <cb>           # Build + run natif
ms web <cb>           # Build + serve WASM
ms upload <cb>        # Build + upload Teensy
ms monitor <cb>       # Monitor serial
ms clean [cb]         # Clean artifacts
ms update             # Update repos/tools/deps
ms status/changes     # Git status multi-repo
ms bridge             # Lance oc-bridge TUI
ms core               # Alias: upload core
ms bitwig             # Alias: upload bitwig
ms icons <cb>         # Generate icon fonts
ms completion <shell> # Shell completions
ms r/w/b              # Aliases courts
```

### C. Outils gérés

| Outil | Source | Requis pour |
|-------|--------|-------------|
| cmake | GitHub Kitware/CMake | developer |
| ninja | GitHub ninja-build/ninja | developer |
| zig | ziglang.org | developer |
| bun | GitHub oven-sh/bun | developer |
| jdk | Adoptium | developer |
| maven | Apache | developer |
| emscripten | GitHub emsdk | developer |
| platformio | platformio.org | developer |
| SDL2 | GitHub libsdl-org (Windows) | developer |

---

*Document maintenu par Claude. Dernière mise à jour: 2025-01-24*
