# Phase 7: CI matrix (multi-platform validation)

**Scope**: CI + smoke tests
**Status**: started
**Created**: 2026-01-27
**Updated**: 2026-01-28

## Goal

- Validate support on:
  - windows-latest
  - ubuntu-latest
  - fedora-latest
  - macos-latest

## Planned commits (atomic)

1. `ci: add smoke matrix (ubuntu/fedora/windows/macos)`
   - `uv run ms setup --dry-run`
   - `uv run ms check`
   - `uv run pytest ms/test -q`

2. `ci: add real builds where feasible`
   - Ubuntu/Fedora: install deps (apt/dnf) then:
     - `ms build core --target wasm`
     - `ms build core --target native`
   - Windows: wasm build at least
   - macOS: native build via CLT

## Work log

- 2026-01-27: Phase created (no CI changes yet).

- 2026-01-27:
  - Added GitHub Actions workflow running a cross-platform smoke matrix.
  - Validates: `uv sync --frozen --extra dev`, `uv run pyright`, `uv run pytest ms/test -q`.
  - Runs safe CLI smoke in dry-run mode (`ms setup --dry-run`, `ms sync --tools --dry-run`, `ms sync --repos --dry-run`).
  - Runs `ms check` as informational (non-blocking) because full workspace repos/toolchains are not present in CI by default.

- 2026-01-27:
  - Added a separate full-build workflow (manual/scheduled) that clones repos, installs toolchains, and builds `core`.
  - Targets per OS: Ubuntu/Fedora = native+wasm, Windows = wasm, macOS = native.

- 2026-01-28:
  - Fixed Fedora CI type-check by installing `libatomic` (required by the bundled Node used by pyright).

- 2026-01-28:
  - Adjusted Full Builds matrix:
    - Native builds on all OS targets (Windows/macOS/Linux).
    - WASM builds only on Ubuntu.
    - Added Bitwig simulator builds (native everywhere, wasm on Ubuntu).
  - Added a Pages deploy job to publish the demo site artifacts.
  - Fixed Pages deploy to use deterministic artifact paths and validate expected WASM outputs.

## Decisions

- Keep CI fast: validate ms package (tests + typing) on all OS targets; don't auto-install heavy toolchains (emsdk) in the smoke job.
- Full Builds is allowed to be heavier; it should reflect real developer workflows (clone repos + toolchains + builds).

## Plan deviations

- In CI, `ms check` is informational for now (non-blocking) because the workspace repos (`open-control/`, `midi-studio/`) are external clones and full toolchain installs (notably emsdk) are too heavy for the basic smoke matrix.

## Verification (minimum)

- CI green on all OS targets.

## Sources

- `.github/workflows/ci.yml`
- `.github/workflows/builds.yml`
