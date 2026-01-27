# Phase 4: Bridge prebuilt (no Rust prereq)

**Scope**: bridge install/run + setup
**Status**: planned
**Created**: 2026-01-27
**Updated**: 2026-01-27

## Goal

- `ms setup` installs `oc-bridge` without requiring Rust/cargo.
- Default path is prebuilt download (GitHub releases).
- Build-from-source remains optional for bridge contributors.

## Planned commits (atomic)

1. `feat(bridge): install oc-bridge from GitHub releases`
   - Download correct asset for OS/arch.
   - Install to `bin/bridge/oc-bridge(.exe)`.
   - Copy `open-control/bridge/config` when available.

2. `refactor(setup): bridge step uses installer, not cargo`
   - Update `SetupService` and `PrereqsService` to not require Rust.

3. `refactor(check): remove rust/cargo as required tools`
   - `ToolsChecker`: rust/cargo become optional.
   - `WorkspaceChecker`: hint changes from `bridge build` to `bridge install`.

## Work log

- 2026-01-27: Phase created (no code changes yet).

## Decisions

- (pending)

## Plan deviations

- (none)

## Verification (minimum)

```bash
uv run pytest ms/test -q
uv run ms setup --dry-run
uv run ms check
```

Manual validation checklist:

- With no Rust installed: `ms setup` succeeds and installs `bin/bridge/oc-bridge`.

## Sources

- `ms/services/bridge.py`
- `open-control/bridge/README.md`
- `open-control/bridge/config/default.toml`
