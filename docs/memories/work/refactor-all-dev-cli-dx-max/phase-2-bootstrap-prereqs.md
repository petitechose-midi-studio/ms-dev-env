# Phase 2: Bootstrap prereqs (uv-only launch)

**Scope**: prereqs + system install + hints
**Status**: planned
**Created**: 2026-01-27
**Updated**: 2026-01-27

## Goal

- `uv run ms setup` can start with only `uv` available.
- If `git` is missing, `ms` guides installation and can execute safe install commands.
- `ms` never runs arbitrary shell snippets; only allowlisted installers.

## Planned commits (atomic)

1. `refactor(prereqs): require only what is needed per step`
   - Remove `gh` requirement.
   - Remove rust toolchain requirement (bridge will be prebuilt later).
   - Gate `git` only when needed (repo sync, emsdk git install).

2. `feat(prereqs): install git automatically when safe`
   - Windows: prefer `winget install --id Git.Git -e` when available.
   - macOS: `xcode-select --install` (interactive, must stop+relaunch).
   - Ubuntu: `sudo apt install -y git`
   - Fedora: `sudo dnf install -y git`

3. `feat(install): group package installs per manager (apt/dnf/winget)`
   - Group packages into a single command per package manager.
   - Deduplicate packages.

## Work log

- 2026-01-27: Phase created (no code changes yet).

## Decisions

- (pending)

## Plan deviations

- (none)

## Verification (minimum)

```bash
uv run pytest ms/test -q
uv run ms prereqs --dry-run
uv run ms setup --dry-run
```

Manual validation checklist:

- Windows fresh shell:
  - With no `git` in PATH: `ms prereqs --install` proposes `winget` or a manual URL.
- Ubuntu/Fedora:
  - `ms prereqs --install` proposes `sudo apt/dnf install ...`.

## Sources

- `ms/services/prereqs.py`
- `ms/services/system_install.py`
- `ms/services/checkers/tools.py`
- `ms/services/checkers/system.py`
- `ms/data/hints.toml`
