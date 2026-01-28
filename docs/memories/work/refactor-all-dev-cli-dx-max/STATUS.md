# Refactor: Dev CLI DX Max - Status

**Scope**: all
**Status**: started
**Created**: 2026-01-27
**Updated**: 2026-01-28

## Goal

- Unifier `ms` autour de `uv run ms ...`
- Minimiser les prerequis (bootstrap = uv only; git install guide)
- Deshelliser les workflows (no bash dependency)
- Support valide: windows-latest, ubuntu-latest, fedora-latest, macos-latest

## Phases

- Phase 1 (deshellize): completed
- Phase 2 (bootstrap prereqs): completed
- Phase 3 (repos git-only): completed
- Phase 4 (bridge prebuilt): completed
- Phase 5 (macos without brew): completed
- Phase 5a (type-safety contract): completed
- Phase 6 (cli unified verbs): completed
- Phase 7 (ci matrix): started
- Phase 8 (web demos): started

## Latest verification

- 2026-01-27 (windows, phase-6):
  - `uv run ms --help` ok (no legacy core/bitwig commands)
  - `uv run ms list` ok
  - `uv run ms build bitwig --target extension --dry-run` ok
  - `pyright` -> 0 errors
  - `uv run pytest ms/test -q` -> 918 passed, 7 skipped, 6 deselected

- 2026-01-27 (windows, phase-5a):
  - `pyright` -> 0 errors
  - `uv run pytest ms/test -q` -> 918 passed, 7 skipped, 6 deselected

- 2026-01-27 (windows, phase-4):
  - `uv run ms bridge --help` ok
  - `uv run ms setup --dry-run` ok
  - `uv run ms check` ok (rustc/cargo hidden from PATH -> optional warnings)
  - `uv run pytest ms/test -q` -> 917 passed, 7 skipped, 6 deselected

- 2026-01-27 (windows):
  - `uv run ms --help` ok
  - `uv run ms where` ok
  - `uv run ms self --help` ok
  - `uv run ms check` ok
  - `uv run oc-build --help` ok
  - `uv run oc-upload --help` ok
  - `uv run oc-monitor --help` ok
  - `uv run ms setup --dry-run --install-cli --update-shell --remember-workspace` ok
  - `uv run ms prereqs --help` ok
  - `uv run ms prereqs --dry-run` ok
  - `uv run ms sync --repos --dry-run` ok
  - `uv run pytest ms/test -q` -> 915 passed, 7 skipped, 6 deselected (network)

## Notes

- Any deviation from the plan must be documented in the relevant phase file under "Plan deviations".

- Repo migration plan: `docs/memories/work/refactor-all-dev-cli-dx-max/repo-migration.md`
