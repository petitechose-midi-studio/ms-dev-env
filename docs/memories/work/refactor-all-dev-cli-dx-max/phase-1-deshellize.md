# Phase 1: Deshellize

**Scope**: ms (hardware + platform utilities) + repo hygiene
**Status**: started
**Created**: 2026-01-27
**Updated**: 2026-01-27

## Goal

- `ms` does not depend on bash/Git Bash for any workflow.
- Hardware workflows use PlatformIO directly from Python.
- No `shell=True` in our subprocess usage.
- Legacy entrypoints removed.

## Planned commits (atomic)

1. `chore(repo): remove bootstrap shell entrypoints`
   - Delete `setup-minimal.sh`
   - Delete `commands/`

2. `refactor(hardware): run PlatformIO directly (no oc-* scripts)`
   - Rewrite `ms/services/hardware.py` to call `pio` directly
   - Remove all `bash` usage and `open-control/cli-tools` dependency

3. `feat(hardware): add env selection + defaults`
   - Add `--env` for teensy builds (dev/release)
   - Default: read `platformio.ini` `default_envs`, fallback `dev`

4. `test(hardware): add cross-platform command construction tests`
   - Tests that do not call real PlatformIO

5. `fix(platform): remove shell=True usage`
   - Fix `ms/platform/clipboard.py`

## Work log

- 2026-01-27:
  - Removed bootstrap shell entrypoints (`setup-minimal.sh`, `commands/*`).
  - Verified: `uv run ms --help`, `uv run pytest ms/test -q`.

## Decisions

- (pending)

## Plan deviations

- (none)

## Verification (minimum)

Run after each commit:

```bash
uv run pytest ms/test -q
uv run ms --help
uv run ms check
```

After commit 2 (hardware deshellized):

```bash
uv run ms core --build --dry-run
uv run ms bitwig --build --dry-run
```

## Sources

- `ms/services/hardware.py`
- `open-control/cli-tools/bin/oc-build`
- `open-control/cli-tools/lib/common.sh`
- `ms/platform/clipboard.py`
- `setup-minimal.sh`
- `commands/`
