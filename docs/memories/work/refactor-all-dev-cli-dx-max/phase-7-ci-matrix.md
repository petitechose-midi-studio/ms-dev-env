# Phase 7: CI matrix (multi-platform validation)

**Scope**: CI + smoke tests
**Status**: planned
**Created**: 2026-01-27
**Updated**: 2026-01-27

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

## Decisions

- (pending)

## Plan deviations

- (none)

## Verification (minimum)

- CI green on all OS targets.

## Sources

- `.github/workflows/*` (to be added)
