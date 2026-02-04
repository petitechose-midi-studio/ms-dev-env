# Phase 02c: Distribution - Full Assets + Bundle Layout Fix + Asset Reuse

Status: DONE

## Goal

Make the distribution pipeline support the full v1 product set *and* avoid rebuilding/reuploading unchanged assets.

This phase locks down the end-user contract so Phase 05/06 can be implemented without ambiguity.

Reference contract:

- `docs/memories/work/ms-user-release-workflow/contract-distribution-v1.md`

## Why This Phase Exists

Two hard requirements surfaced during audit:

1) Bundle layout must match oc-bridge config discovery.
   - oc-bridge searches for `config.toml` / `config/**` next to the executable.
   - Therefore the bundle must ship config under `bin/config/**`.

2) We must support selective rebuilds.
   - Example: `plugin-bitwig` changes frequently while `core` stays unchanged.
   - We want new tags to include all assets.
     - stable/beta: self-contained tags via copy reuse (no dependency chain)
     - nightly: quota-efficient URL reuse via `assets[].url`

## Deliverables

### A) Bundle layout fix (required)

Update bundle packaging so the zip contains:

```
bin/
  oc-bridge[.exe]
  midi-studio-loader[.exe]
  config/
    default.toml
    devices/teensy.toml
```

The previous `bridge/config/**` layout is invalid for oc-bridge.

### B) Full v1 assets in every tag

For each tag, publish:

- Bundles (OS/arch): `midi-studio-<os>-<arch>-bundle.zip`
- Firmware:
  - `midi-studio-default-firmware.hex`
  - `midi-studio-bitwig-firmware.hex`
- Bitwig extension:
  - `midi_studio.bwextension`
- `manifest.json` + `manifest.json.sig`

### C) Asset reuse (build only what changed)

Implement a reuse planner that:

- selects the previous tag within the same channel
- verifies the previous manifest signature
- decides build vs reuse per asset group
- emits a new signed manifest with:
  - reused assets copied with `sha256/size` from the previous manifest
  - nightly-only: reused assets setting `assets[].url` to the previous release asset URL

For stable/beta, we use **copy reuse**:

- download the reused assets from a previous tag
- re-upload them to the current tag
- build the manifest from the local files (so assets are fetched from the current tag)

## Implementation Plan (ordered)

1) Update distribution packaging script

- Change `scripts/package_bundle.py` to place oc-bridge config under `bin/config/**`.
- Add a CI check that validates the bundle zip contains `bin/config/default.toml`.

2) Extend distribution release-spec generation (ms-dev-env)

- Update `ms-dev-env` release spec writer to include:
  - repos: `loader`, `oc-bridge`, `core`, `plugin-bitwig`
  - assets: bundles + both firmware files + bitwig extension
  - install_sets:
    - `default` includes bundle + `midi-studio-default-firmware.hex`
    - `bitwig` includes bundle + `midi-studio-bitwig-firmware.hex` + `midi_studio.bwextension`

Files:

- `ms/services/release/config.py`
- `ms/services/release/spec.py`

3) Extend distribution workflows to build firmware + bitwig extension

- `publish.yml`:
  - keep the OS matrix job for bundles
  - add an Ubuntu job that builds:
    - `core` firmware (default)
    - `plugin-bitwig` firmware (bitwig)
    - Bitwig extension `.bwextension`
  - upload these artifacts as workflow artifacts

- `nightly.yml`:
  - same structure
  - uses “latest green CI” SHAs selection for repos that declare `required_ci_workflow_file`
  - for repos without CI gating, pins the branch head SHA and relies on the distribution build as the guardrail

4) Add reuse planner + manifest builder

Add a small script (recommended: Python) in the distribution repo:

- `scripts/build_manifest_with_reuse.py`

Responsibilities:

- read release spec
- locate previous tag (same channel)
- download previous `manifest.json` + `.sig`
- verify signature (use `ms-dist-manifest verify`)
- compute recipe fingerprint for previous tag vs HEAD (git show + sha256)
- decide which groups changed (compare pinned repo SHAs in manifest.repos)
- write a new `manifest.json` (schema=2)
  - built assets: compute sha256/size from local files
  - reused assets: copy sha256/size from previous manifest and set `url`

Then the workflow:

- signs the manifest (`ms-dist-manifest sign`)
- verifies signature (`ms-dist-manifest verify`)
- stable/beta: publishes all assets (built or copied) + `manifest.json(.sig)`
- nightly: may publish only changed assets + `manifest.json(.sig)` (reused via `assets[].url`)

5) Documentation updates

- Ensure the contract is referenced from:
  - `docs/memories/work/ms-user-release-workflow/README.md`
  - `docs/memories/work/ms-user-release-workflow/phase-04-ms-manager-foundation.md`
  - `docs/memories/work/ms-user-release-workflow/phase-05-transaction-engine.md`

## Exit Criteria

- A tag contains all v1 assets via the manifest:
  - bundles (OS/arch)
  - firmware default + bitwig
  - bitwig extension
  - signed manifest
- Bundles ship oc-bridge config under `bin/config/**` and oc-bridge loads it.
- Reuse works:
  - changing only `plugin-bitwig` rebuilds only `firmware-bitwig` + `.bwextension`
  - changing only `core` rebuilds `firmware-default` and `firmware-bitwig`
  - changing only `loader` or `oc-bridge` rebuilds only bundles
  - nightly: unchanged assets are referenced via `assets[].url`
  - stable/beta: unchanged assets are copied + reuploaded (tag is self-contained)

Validated:

- beta full build (all v1 assets published):
  - `petitechose-midi-studio/distribution` tag `v0.0.1-beta.6`
- beta copy reuse (builds skipped, assets copied from previous tag, manifest has no `assets[].url`):
  - `petitechose-midi-studio/distribution` tag `v0.0.1-beta.8`
- nightly behavior:
  - skip publish when unchanged vs previous nightly
  - `assets[].url` reuse enabled for quota efficiency

## Tests

Required CI checks:

- Validate produced `manifest.json` against `schemas/manifest.schema.json`.
- Verify signature on the produced manifest.
- Smoke: unzip one bundle and check expected paths exist.

CI helper scripts:

- `distribution/scripts/validate_dist.py` validates the dist directory against the release spec and bundle layout.
- `distribution/scripts/verify_manifest_assets.py` validates a dist directory against `manifest.json` (sha256/size + bundle layout).

Manual smoke (one OS is enough for contract validation):

- Download a bundle zip, extract it.
- Run `./bin/oc-bridge --daemon` and verify it reads `./bin/config/default.toml` (no unexpected config regeneration).

## Progress (recorded)

- Bundle layout fix implemented in `petitechose-midi-studio/distribution`:
  - `distribution/scripts/package_bundle.py` now zips oc-bridge config under `bin/config/**`.
- Asset reuse planner + manifest builder implemented:
  - `distribution/scripts/build_manifest_with_reuse.py`
- Workflows updated (WIP until merged + CI validated):
  - `distribution/.github/workflows/publish.yml`:
    - adds a `plan` job (reuse vs build)
    - adds `build_integrations` (PlatformIO firmware + Bitwig extension)
    - builds manifest via `build_manifest_with_reuse.py build`
    - stable/beta: copy reuse (materialize reused assets + publish self-contained tags)
    - fix: ensure the gated release job still runs when build jobs are skipped (reuse-only releases)
  - `distribution/.github/workflows/nightly.yml`:
    - same reuse plan + integrations build + manifest-with-reuse
    - publish only if the reuse plan requires any builds (skip if pins unchanged)
  - `distribution/release-specs/nightly.template.json` expanded (core + plugin-bitwig + firmware + bitwig extension)
  - `distribution/scripts/select_latest_green.py` supports repos without CI gating by pinning the branch head SHA
- Maintainer release command updated in `ms-dev-env`:
  - release spec now includes `core` and `plugin-bitwig` repos and the v1 assets/install_sets.
