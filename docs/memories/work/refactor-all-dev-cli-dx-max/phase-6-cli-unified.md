# Phase 6: CLI unified verbs

**Scope**: ms CLI surface
**Status**: completed
**Created**: 2026-01-27
**Updated**: 2026-01-27

## Goal

- Single coherent CLI surface (no app-specific mode puzzles).
- Verbs are consistent across apps:
  - `list`, `build`, `run`, `web`, `upload`, `monitor`, `bridge`.
- All hints point to real commands.

## Planned commits (atomic)

1. `refactor(cli): verb-based commands`
   - Add:
      - `ms list`
      - `ms build <app> --target native|wasm|teensy|extension`
      - `ms run <app>`
      - `ms web <app> [--port]`
      - `ms upload <app> [--env]`
      - `ms monitor <app> [--env]`

2. `refactor(cli): remove app-specific core/bitwig top-level commands`
   - Remove `ms core` / `ms bitwig`.

3. `fix(hints): remove phantom commands; align hints to real CLI`

## Work log

- 2026-01-27: Phase created (no code changes yet).

- 2026-01-27:
  - Added verb commands: `ms list`, `ms build`, `ms run`, `ms web`, `ms upload`, `ms monitor`.
  - Bitwig extension is now handled via `ms build bitwig --target extension`.
  - Removed legacy app-specific entrypoints: `ms core`, `ms bitwig`.
  - Aligned all hints to real commands (e.g. `ms sync --tools`).

## Decisions

- No legacy aliases: only the verb-based commands are exposed.
- Bitwig extension deploy is modeled as `ms build bitwig --target extension`.

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
