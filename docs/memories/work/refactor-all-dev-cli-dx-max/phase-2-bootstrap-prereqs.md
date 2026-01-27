# Phase 2: Bootstrap + Global CLI (uv tool)

**Scope**: prereqs + system install + hints + global CLI install + workspace default
**Status**: started
**Created**: 2026-01-27
**Updated**: 2026-01-27

## Goal

- `ms` and `oc-*` are usable without `uv run` (optional global install via `uv tool`).
- `ms` is useful outside the workspace tree by remembering a single default workspace root.
- Workspace resolution order is explicit and predictable:
  - `--workspace` (CLI) / `WORKSPACE_ROOT` (env)
  - cwd upward search for `.ms-workspace`
  - remembered default workspace
- `uv run ms ...` remains the canonical, non-invasive entrypoint (no global install required).
- If `git` is missing, `ms` guides installation and can execute safe allowlisted install commands.
- `ms` never runs arbitrary shell snippets; only allowlisted installers.

## Planned commits (atomic)

1. `feat(workspace): remember default workspace`
   - Add a small user-level config file storing `workspace_root` (single).
   - Add commands:
     - `ms use [PATH]` (default: `.`)
     - `ms where`
     - `ms forget`
   - Update `ms` context building to fall back to remembered workspace when cwd/env do not resolve.

2. `feat(self): install/uninstall ms via uv tool`
   - Add commands:
     - `ms self install` (installs `ms` + `oc-*` globally via `uv tool install`)
     - `ms self uninstall` (removes global commands via `uv tool uninstall`)
   - Add optional helper:
     - `ms self update-shell` (runs `uv tool update-shell`)
   - Ensure the UX is explicit about what is modified (PATH) and how to revert.

3. `feat(setup): optionally install CLI and remember workspace`
   - Add `ms setup` flags:
     - `--install-cli` (calls `ms self install`)
     - `--update-shell` (calls `ms self update-shell`)
     - `--remember-workspace` (calls `ms use .`)
   - Default behavior stays non-invasive (no global install without an explicit flag).

4. `refactor(prereqs): require only what is needed per step`
   - Gate `git` only when needed (repo sync, emsdk git install).
   - Keep `gh` and Rust requirements as-is for now.
     - Dropping `gh` is Phase 3.
     - Dropping Rust/cargo is Phase 4.

5. `feat(prereqs): install git automatically when safe`
   - Windows: prefer `winget install --id Git.Git -e` when available.
   - macOS: `xcode-select --install` (interactive, must stop+relaunch).
   - Ubuntu: `sudo apt install -y git`
   - Fedora: `sudo dnf install -y git`

6. `feat(install): group package installs per manager (apt/dnf/winget)`
   - Group packages into a single command per package manager.
   - Deduplicate packages.

7. `feat(self): wipe/destroy workspace (explicit)`
   - Add safe cleanup verbs for end-users:
     - `ms wipe` deletes generated artifacts only (e.g. `.ms/`, `tools/`, `bin/`, `.build/`).
     - `ms destroy` is an explicit, confirmed operation to delete the entire workspace directory.
   - Keep defaults non-destructive; require confirmation / `--yes`.

## Work log

- 2026-01-27: Phase created (no code changes yet).

- 2026-01-27:
  - Added user-level default workspace memory.
  - Added `ms use`, `ms where`, `ms forget`.
  - Added global `--workspace` override (maps to `WORKSPACE_ROOT` for the current invocation).

- 2026-01-27:
  - Added `ms self install|uninstall|update-shell` to manage global installation via `uv tool`.

- 2026-01-27:
  - Added `ms setup` flags: `--install-cli`, `--update-shell`, `--remember-workspace`.

- 2026-01-27:
  - Added `ms wipe` (generated artifacts) and `ms destroy` (delete workspace) with dry-run-by-default safety.

- 2026-01-27:
  - Refined `git` gating: required only for repo sync or git-based tool installs (emsdk clone).
  - Improved Git install hints:
    - Windows: prefer `winget install --id Git.Git -e` when available.
    - Ubuntu/Fedora: `sudo apt/dnf install -y git`.
  - Grouped and de-duplicated safe install steps per package manager (apt/dnf/pacman/brew).

- 2026-01-27:
  - Removed unsafe `curl | sh` / `powershell | iex` snippets from `hints.toml`.
    - Windows: prefer `winget install --id astral-sh.uv -e` for uv.
    - macOS: prefer `brew install uv` for uv.
  - Added `ms self uninstall --name` override and improved tool name resolution.

## Decisions

- Store the default workspace root in a dedicated user config file: `<user_config_dir>/workspace.toml`.

## Plan deviations

- (none)

## Verification (minimum)

```bash
uv run pytest ms/test -q
uv run ms --help
uv run ms check
uv run ms prereqs --dry-run
uv run ms setup --dry-run
```

Manual validation checklist:

- Global install:
  - From workspace root: `uv tool install -e .`
  - Ensure PATH: `uv tool update-shell`
  - From a random directory: `ms where` resolves to remembered workspace.
  - From inside a PlatformIO project: `oc-build` finds `platformio.ini`.

- Prereqs install:
  - Windows fresh shell:
    - With no `git` in PATH: `ms prereqs --install` proposes `winget` or a manual URL.
  - Ubuntu/Fedora:
    - `ms prereqs --install` proposes `sudo apt/dnf install ...`.

Opt-in network tests:

```bash
uv run pytest -m network
```

## Sources

- `ms/services/prereqs.py`
- `ms/services/system_install.py`
- `ms/services/checkers/tools.py`
- `ms/services/checkers/system.py`
- `ms/cli/context.py`
- `ms/core/workspace.py`
- `ms/core/user_workspace.py`
- `ms/cli/commands/workspace.py`
- `ms/cli/app.py`
- `ms/cli/commands/self_cmd.py`
- `ms/cli/commands/setup.py`
- `ms/cli/commands/wipe.py`
- `ms/data/hints.toml`
