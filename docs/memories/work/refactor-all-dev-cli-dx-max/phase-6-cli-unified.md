# Phase 6: CLI unified verbs

**Scope**: ms CLI surface
**Status**: planned
**Created**: 2026-01-27
**Updated**: 2026-01-27

## Goal

- Single coherent CLI surface (no app-specific mode puzzles).
- Verbs are consistent across apps:
  - `list`, `build`, `run`, `web`, `upload`, `monitor`, `bridge`, `bitwig`.
- All hints point to real commands.

## Planned commits (atomic)

1. `refactor(cli): verb-based commands`
   - Add:
     - `ms list`
     - `ms build <app> --target native|wasm|teensy`
     - `ms run <app>`
     - `ms web <app> [--port]`
     - `ms upload <app> [--env]`
     - `ms monitor <app> [--env]`

2. `refactor(cli): remove app-specific core/bitwig top-level commands`
   - Remove or reduce `ms core` / `ms bitwig`.

3. `fix(hints): remove phantom commands; align hints to real CLI`

## Work log

- 2026-01-27: Phase created (no code changes yet).

## Decisions

- (pending)

## Plan deviations

- (none)

## Verification (minimum)

```bash
uv run pytest ms/test -q
uv run ms --help
uv run ms check
```

Sanity:

- `ms --help` lists only the unified verbs.
- `ms check` contains no hints to non-existent commands.

## Sources

- `ms/cli/app.py`
- `ms/cli/commands/`
- `ms/data/hints.toml`
