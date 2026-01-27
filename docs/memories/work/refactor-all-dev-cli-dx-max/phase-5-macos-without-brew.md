# Phase 5: macOS without Homebrew requirement

**Scope**: system checks + native build deps on macOS
**Status**: started
**Created**: 2026-01-27
**Updated**: 2026-01-27

## Goal

- `ms check` on macOS does not hard-require Homebrew.
- Native build remains possible:
  - minimum path: Xcode CLT
  - SDL2: either installed manually (brew/other) or fetched by CMake fallback.

## Planned commits (atomic)

1. `refactor(system-check): do not require brew on macos`
   - `SystemChecker` macOS:
     - require C/C++ compiler (CLT) via `xcode-select --install`
     - SDL2 becomes WARNING (with guidance)

2. `build(macos): fetch SDL2 when not found (macOS only)`
   - Add a CMake fallback: if macOS and SDL2 not found, fetch/build SDL2.

## Work log

- 2026-01-27: Phase created (no code changes yet).

- 2026-01-27:
  - `ms check` on macOS no longer hard-requires Homebrew; it checks Xcode CLT and warns on missing SDL2.
  - `midi-studio/core` now fetches SDL2 via CMake FetchContent on macOS when not found.

## Decisions

- (pending)

## Plan deviations

- (none)

## Verification (minimum)

In CI (macos-latest):

```bash
uv run ms check
uv run ms build core --target native
```

## Sources

- `ms/services/checkers/system.py`
- `midi-studio/core/sdl/CMakeLists.txt`
