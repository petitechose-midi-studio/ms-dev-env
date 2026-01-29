# Feature: Distribution Channels + Installer

**Scope**: ms-dev-env + open-control + midi-studio

**Status**: planned

**Created**: 2026-01-29
**Updated**: 2026-01-29

## Intent

Deliver a complete, automatic system for:

- dev bootstrap (uv-only to run the CLI)
- CI parity (all platforms + targets we care about)
- distribution via 2 channels: `nightly` and `release`
- an end-user installer (Rust, TUI/GUI) that manages only final binaries

Non-goal: no new app features (sequencer, preset GUI, etc.) in this phase.

## Current baseline (facts)

- CLI entrypoint: `uv run ms ...`
- One-click dev setup: `uv run ms setup --yes`
  - installs allowlisted system deps when possible
  - syncs repos + toolchains
  - installs prebuilt `oc-bridge` into `bin/bridge/`
  - `uv sync --frozen --extra dev`

- CI smoke: `.github/workflows/ci.yml`
  - ubuntu/windows/macos matrix (GitHub-hosted runners)
  - Fedora tested via container job (no GitHub-hosted fedora runner)

- Full builds (nightly-like): `.github/workflows/builds.yml`
  - schedule daily + manual trigger
  - native builds on all OS
  - wasm build on Ubuntu only
  - Pages deploy for `/demo/<app>/latest/`

## Product contract (distribution)

We ship only final binaries (no toolchains):

- bridge
  - `oc-bridge` (+ config)

- apps
  - native simulators: core + bitwig
  - wasm simulators: core + bitwig
  - Bitwig extension `.bwextension`

- hardware
  - firmware releases
  - uploader CLI (Teensy)

The installer is responsible for OS integration (shortcuts, service install, etc.).

## Channels

### Release

- Trigger: manual
- Output: immutable GitHub Release (tag) + manifest + assets
- Default channel for the installer

### Nightly

- Trigger: schedule daily
- Output: pre-release + manifest + assets
- Guard: build only if changes exist in:
  - `ms-dev-env`, OR
  - any synced repo listed in `ms/data/repos.toml` (open-control/*, midi-studio/*)

## Manifest (source of truth)

Each build publishes a `manifest.json` that contains:

- `channel`: `nightly` | `release`
- `build_id`: date/time + short sha
- `ms_dev_env_sha`
- `repos`: list of `{org, name, url, branch, head_sha}` (same set as `ms/data/repos.toml`)
- `assets`: list of installable artifacts:
  - `id` (stable)
  - `os` / `arch`
  - `kind` (bridge | simulator_native | simulator_wasm | extension | firmware | uploader)
  - `filename`
  - `sha256` + `size`

Rule: the installer never guesses. If it is installable, it is in the manifest.

## Execution plan (phases)

### Phase 0 - Docs coherence

- [x] Clean obsolete memories and fix broken references
- [x] Add a workspace README with "uv-only to run" + system deps guide

### Phase 1 - Artifact contract + manifest schema

- [ ] Define stable asset IDs + filenames (per OS/arch)
- [ ] Implement a manifest generator (produced by CI)
- [ ] Ensure `bin/` layout is deterministic and matches the manifest

### Phase 2 - Nightly channel

- [ ] Add `nightly.yml` with a guard job (skip if no changes in any synced repo)
- [ ] Publish as GitHub pre-release + upload assets + `manifest.json`

### Phase 3 - Release channel

- [ ] Add `release.yml` (manual trigger) with a version/tag input
- [ ] Publish immutable GitHub Release + assets + `manifest.json`
- [ ] Ensure repo SHAs used to build are recorded (no silent drift)

### Phase 4 - End-user installer (Rust)

- [ ] TUI first (simple and robust)
- [ ] Channel/version selection (default: release/latest)
- [ ] Install/update/uninstall/status
- [ ] Integrate bridge service via `oc-bridge install/uninstall` when available

### Phase 5 - Acceptance & QA

- [ ] Test installs on fresh VMs (Windows/macOS/Linux)
- [ ] Validate upgrade paths (nightly -> nightly, release -> release)
- [ ] Document troubleshooting and rollback

## CI / build pipeline changes (planned)

### 1) Split "Full Builds" into two concerns

- Keep Pages deploy as-is (or migrate it to a dedicated workflow).
- Add two explicit distribution workflows:
  - `nightly.yml` (scheduled + guarded)
  - `release.yml` (workflow_dispatch)

### 2) Nightly guard implementation

Compute a deterministic `source_hash` from:

- current `ms-dev-env` git sha
- remote HEAD sha of every repo in `ms/data/repos.toml`

Implementation note:

- Use `git ls-remote <url> refs/heads/<branch>` (git-only, no GH auth dependency).
- Compare against the last published nightly `source_hash` (stored in the last nightly manifest).

If `source_hash` unchanged: skip the heavy build jobs.

### 3) Release determinism

Release builds must be reproducible:

- produce and publish the repo SHAs used to build (in the manifest)
- avoid silently drifting dependencies (toolchains pinned; avoid "latest" where possible)

If we need strict pinning for repos during CI builds, introduce a lock/checkout mode:

- generate a lock (repo SHAs)
- make `ms sync --repos` able to checkout those SHAs in CI

## Installer (planned)

### UX

- Default: channel `release`, version `latest`
- Let the user choose:
  - channel: `release` or `nightly`
  - version within the channel

Actions:

- install
- update
- uninstall
- status (what is installed + versions)

### Implementation

- A Rust binary (TUI first, GUI optional later)
- Downloads `manifest.json`, then downloads assets, verifies sha256, installs to an app-managed directory
- Service integration:
  - reuse `oc-bridge install/uninstall` where available (Windows/Linux today)

## References

- Setup & distribution architecture: `docs/memories/setup-architecture/README.md`
- Teensy uploader CLI roadmap: `docs/memories/work/feature-teensy-uploader-cli/README.md`
- Repo manifest: `ms/data/repos.toml`
- Toolchain pins: `ms/data/toolchains.toml`
- CI smoke: `.github/workflows/ci.yml`
- Full builds: `.github/workflows/builds.yml`
