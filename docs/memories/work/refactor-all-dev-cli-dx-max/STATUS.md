# Refactor: Dev CLI DX Max - Status

**Scope**: all
**Status**: started
**Created**: 2026-01-27
**Updated**: 2026-01-27

## Goal

- Unifier `ms` autour de `uv run ms ...`
- Minimiser les prerequis (bootstrap = uv only; git install guide)
- Deshelliser les workflows (no bash dependency)
- Support valide: windows-latest, ubuntu-latest, fedora-latest, macos-latest

## Phases

- Phase 1 (deshellize): started
- Phase 2 (bootstrap prereqs): planned
- Phase 3 (repos git-only): planned
- Phase 4 (bridge prebuilt): planned
- Phase 5 (macos without brew): planned
- Phase 6 (cli unified verbs): planned
- Phase 7 (ci matrix): planned

## Latest verification

- 2026-01-27 (windows):
  - `uv run ms --help` ok
  - `uv run pytest ms/test -q` -> 896 passed, 7 skipped

## Notes

- Any deviation from the plan must be documented in the relevant phase file under "Plan deviations".
