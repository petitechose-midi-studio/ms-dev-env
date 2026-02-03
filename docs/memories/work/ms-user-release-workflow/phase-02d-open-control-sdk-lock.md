# Phase 02d: OpenControl SDK Lock (Minimal BOM For Firmware Builds)

Status: IN PROGRESS

## Goal

Reduce long-term maintenance cost and release risk by centralizing the OpenControl dependency pins used by MIDI Studio firmware builds.

We want:

- deterministic CI builds (still pinned by commit, not floating branches)
- a single source of truth for the OpenControl pins (no duplication between firmwares)
- a human-friendly semver label for the set (a compatibility set, not "one version for all repos")

This phase is a follow-up to Phase 02c:

- Phase 02c introduced `platformio` `env:release` in `core` and `plugin-bitwig` with pinned OpenControl deps.
- Phase 02d refactors those pins into one shared "oc-sdk lock" file.

## Scope

Only the OpenControl repos actually required by firmware builds:

- `open-control/framework`
- `open-control/hal-common`
- `open-control/hal-teensy`
- `open-control/ui-lvgl`
- `open-control/ui-lvgl-components`

Explicitly out of scope:

- pinning/packaging of `open-control/bridge` (host binary; handled in bundles)
- unrelated OpenControl repos (examples/tools/etc)
- changing OpenControl’s own versioning strategy (repos remain independent)

## Key Idea

Treat "OC SDK" as a **compatibility set** (BOM/lockfile):

- OpenControl repos keep independent history and tags.
- MIDI Studio firmware builds consume a tested set of SHAs.
- A semver `oc_sdk_version` labels the set for humans.
- The build inputs remain SHAs (deterministic).

## Current State (post Phase 02c)

- `petitechose-midi-studio/core` has `platformio.ini` `env:release` with GitHub `git#<sha>` pins.
- `petitechose-midi-studio/plugin-bitwig` has `platformio.ini` `env:release` with GitHub `git#<sha>` pins.
- Pins are duplicated across repos.

Pain points:

- drift risk: pins can diverge across firmwares
- overhead: every OpenControl bump requires edits in multiple repos
- harder preflight: it's not obvious which OpenControl set will be used by CI

## Proposed Design (v1)

### A) Single lock file living in `core`

Create one file in `petitechose-midi-studio/core`:

- `oc-sdk.ini` (name is flexible, must be stable)

It contains:

- `oc_sdk_version = X.Y.Z` (compatibility set version)
- `lib_deps` list with GitHub pins (SHAs)

Example (shape only):

```ini
[oc_sdk]
version = 0.1.0

[oc_sdk_deps]
lib_deps =
    oc-framework=https://github.com/open-control/framework.git#<sha>
    oc-hal-common=https://github.com/open-control/hal-common.git#<sha>
    oc-hal-teensy=https://github.com/open-control/hal-teensy.git#<sha>
    oc-ui-lvgl=https://github.com/open-control/ui-lvgl.git#<sha>
    oc-ui-lvgl-components=https://github.com/open-control/ui-lvgl-components.git#<sha>
```

### B) `platformio.ini` consumes the lock via `extra_configs`

In `core/platformio.ini`:

- `extra_configs = oc-sdk.ini`
- `env:release` uses `lib_deps = ${oc_sdk_deps.lib_deps}`

In `plugin-bitwig/platformio.ini`:

- `extra_configs = ../core/oc-sdk.ini` (CI checks out `core` next to `plugin-bitwig`)
- `env:release` uses `lib_deps = ms-core=symlink://../core` + `${oc_sdk_deps.lib_deps}`

Result:

- the OpenControl pins exist in exactly one place
- both firmwares build against the same OpenControl set

### C) Version semantics

`oc_sdk_version` is a label for the set.

- bump `PATCH` when any OpenControl SHA changes but API compatibility is expected
- bump `MINOR` when OpenControl changes require small MIDI Studio adjustments
- bump `MAJOR` for breaking changes

This does not constrain OpenControl repo semver/tagging.

## Release / CI Interaction

- The distribution release spec pins:
  - `core@sha`
  - `plugin-bitwig@sha`

- In CI, PlatformIO `env:release` resolves OpenControl deps from the lock file contained in the pinned `core@sha`.

So "which OpenControl set did we ship" is fully determined by:

- `core@sha` (contains `oc-sdk.ini`)
- `plugin-bitwig@sha` (contains Bitwig firmware sources)

## Developer Experience (DX) Guardrails (follow-up work)

Add a preflight in `ms release` (stable/beta) that:

- detects dirty repos under `open-control/*` (dev symlink edits)
- warns if the local OpenControl HEAD SHAs differ from the `oc-sdk.ini` pins used by `env:release`
- blocks by default for stable/beta (override flag required)

Implementation note:

- CLI override flag: `ms release prepare --allow-open-control-dirty`

Goal: prevent "dev symlink tests != CI release build" surprises.

## Work Items (ordered, testable)

### 1) Implement oc-sdk lock file (core)

- Add `oc-sdk.ini` to `petitechose-midi-studio/core`.
- Refactor `core/platformio.ini`:
  - `env:release` uses `extra_configs` and reads `lib_deps` from the lock.

Success metrics:

- `core/platformio.ini` contains zero `https://github.com/open-control/...#` entries.
- `python -m platformio run -e release` succeeds in CI (distribution build_integrations job).

### 2) Consume the lock file (plugin-bitwig)

- Refactor `plugin-bitwig/platformio.ini`:
  - remove duplicated OpenControl pins
  - include `../core/oc-sdk.ini`

Success metrics:

- `plugin-bitwig/platformio.ini` contains zero duplicated OpenControl pins.
- `python -m platformio run -e release` succeeds in CI (distribution build_integrations job).
- Both firmwares resolve identical OpenControl SHAs (validated via PlatformIO package list in CI logs).

### 3) Add ms release preflight (ms-dev-env)

- Add a check in `ms release plan/prepare`:
  - detect dirty `open-control/*` repos
  - detect mismatch between local OpenControl HEAD and `oc-sdk.ini`

Success metrics:

- stable/beta releases block on mismatch unless explicitly overridden.
- unit tests cover mismatch detection and messaging.

### 4) Optional: bump helper

- Add a helper command/script that updates `oc-sdk.ini` pins from:
  - local workspace OpenControl HEADs, or
  - "latest green" selection (if/when OpenControl CI gating is standardized)

Success metrics:

- 1 command updates the lock file + increments `oc_sdk_version` + opens PR(s).

## Exit Criteria

- OpenControl firmware deps are defined in exactly one place (`core/oc-sdk.ini`).
- CI firmware builds use only pinned SHAs (no floating branches).
- Bumping OpenControl for MIDI Studio requires editing one file (the lock) and is auditable.
- ms release warns/blocks when local symlink dev diverges from release pins.

## Progress (recorded)

- `petitechose-midi-studio/core`:
  - added `oc-sdk.ini`
  - `platformio.ini` `env:release` reads `${oc_sdk_deps.lib_deps}` via `extra_configs`
- `petitechose-midi-studio/plugin-bitwig`:
  - `platformio.ini` includes `../core/oc-sdk.ini` via `extra_configs`
  - `env:release` consumes `${oc_sdk_deps.lib_deps}` and removed duplicated OpenControl pins
