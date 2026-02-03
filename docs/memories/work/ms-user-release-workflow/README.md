# MS User Release Workflow (Plan + Tracking)

This folder defines the end-user distribution workflow for MIDI Studio:

- A dedicated public distribution repo (GitHub Releases + GitHub Pages)
- A stable bootstrap installer
- A GUI app manager (`ms-manager`, Tauri + Svelte)
- Firmware flashing via `midi-studio-loader` (JSON contract)
- oc-bridge service lifecycle management (with MIDI-Studio-specific service name)
- A safe nightly pipeline (skip if not fully green)

This file is the entry point.

## How To Use This Plan (required)

Before doing any work:

1) Re-validate that previously completed phases are actually done.
   - Read each phase file listed as DONE and verify its exit criteria against reality.
   - If a mismatch exists, stop and trace back: identify the first phase whose exit criteria are not met, mark that phase as IN PROGRESS, and resume from there.

2) Re-validate that phases listed as TODO are still needed.
   - If the codebase evolved (new workflows, moved repos, renamed artifacts), update the tracking first.

3) After each phase:
   - Run the full test checklist for that phase.
   - Update this tracking file: mark phase DONE, record notable decisions, and link to relevant PRs/commits.

## Non-Negotiable Invariants

- Reproducible releases: a bundle tag must map to exact repo SHAs (recorded in manifest).
- Safe-by-default updates: verify signatures + hashes; atomic switch of `current/`; rollback on failure.
- Nightly safety: publish only if all required CI checks are green and the distribution build passes.
- Never leave the bridge paused: any flash attempt must end with oc-bridge resumed (success/fail/cancel).
- Minimal end-user friction:
  - default channel = stable
  - default install/update = latest stable bundle (when stable exists)
  - stable `current/` path for shortcuts and services
- Open-source friendly:
  - public repos
  - clear workflows
  - clean contributor docs

## Current Baseline (already true today)

These are prerequisites we rely on.

- `midi-studio/loader` has an installer-friendly JSON contract:
  - `list --json` emits a single `{schema,event:"list"}` event.
  - `flash`/`reboot` emit `operation_summary` at the end.
    - Note: `flash --dry-run` intentionally ends at `dry_run` (no `operation_summary`).
  - JSON supports `--json-timestamps` and `--json-progress`.
  - Recent loader commits (baseline):
    - `eb56bc0` feat!: simplify JSON contract for list and target records
    - `a252634` feat: add operation summary JSON event

- `open-control/bridge` provides:
  - local control plane (`oc-bridge ctl pause|resume|status`)
  - Windows/Linux service install/uninstall with configurable `--service-name`
  - Windows/Linux support `--service-exec <absolute_path>` so installed services/units can point
    to a stable `current/` path (atomic upgrades)
  - Linux: `--no-desktop-file` to skip installing a `.desktop` launcher

- `ms-dev-env` already has CI workflows that build and package artifacts (dev-oriented). We will not ship ms-dev-env to end users.

## Decisions (locked)

- Distribution uses a dedicated repo (GitHub Releases + Pages).
- Bundles are cohesive: end user selects a bundle tag (not per-component versions).
- Channels: stable/beta/nightly.
- Channel selection UX (v1):
  - Channel selector is exclusive (stable | beta | nightly).
  - Default on first launch: stable.
  - Persist selected channel; updates are received only from the selected channel.
- Default install/update + rollback (v1):
  - Resolve "latest" for the selected channel via GitHub Releases API.
  - Stable may use GitHub Releases `latest` when it exists, but must handle "no stable yet" (404) gracefully.
  - Advanced selection/rollback lists tags via GitHub Releases API (filtered by channel).
- Channel pointers (`channels/*.json`) are removed. They were operationally costly (manual updates) and not required for trust (manifest signature + sha256).

- Bundle layout (locked): oc-bridge config must be discoverable by oc-bridge.
  - Bundle zips must ship config under `bin/config/**`.
  - Previous layout `bridge/config/**` is invalid for oc-bridge.

- Asset reuse (locked): unchanged assets can be reused without rebuilding.
  - stable/beta: copy reuse (self-contained tags; assets are re-uploaded)
  - nightly: URL reuse (quota-efficient) via `manifest.assets[].url`
  - Reuse is same-channel only (stable->stable, beta->beta, nightly->nightly).
  - stable/beta must never reference nightly assets.

- Profiles (v1+):
  - A release tag can expose multiple install "profiles" via `install_sets`.
  - `install_set.id` is the profile id:
    - `default` = Standalone (core-only) and is required in every manifest.
    - additional ids (future): `bitwig`, `ableton`, `flstudio`, `reaper`, ...
  - Only one profile is installed/active on the controller at a time (device memory constraint).
  - Runtime behavior: the controller remains usable in standalone mode by default; DAW-specific behavior activates when the DAW/extension is running.

Reference:
- `docs/memories/work/ms-user-release-workflow/contract-install-profiles-and-daw-packages.md`
- `docs/memories/work/ms-user-release-workflow/contract-distribution-v1.md`
- Release bundle build (v1):
  - Rust binaries are built with size-focused release settings.
  - `midi-studio-loader` in bundles is built without default features (`--no-default-features --features cli`).
- Nightly selection: per repo, pick the latest commit with CI success; skip nightly if any repo lacks a green commit.
- Nightly publish is conditional:
  - if the resolved pinned SHAs are unchanged vs the previous published nightly (reuse plan => no builds), publish nothing.
  - if the nightly tag already exists (rerun), publish nothing.
- macOS/Linux: user services when possible.
- Windows: admin allowed; service points to stable `current/`.
- oc-bridge remains agnostic; MIDI Studio requires service-name configurability to avoid collisions.
- ms-manager GUI: Tauri + Svelte.
- ms-manager supported platforms (v1):
  - Windows: Windows 10+ (x86_64).
  - macOS: macOS 13+.
  - Linux (WebKitGTK 4.1): Debian 13+, Ubuntu 24.04+, Fedora current, RHEL-family 10+.
  - Not supported: RHEL 9.
- Windows installer (v1): use WebView2 `downloadBootstrapper`.
- macOS/Linux symlinks: install to `/usr/local/bin` (sudo) for frictionless CLI usage.

## Phases (tracking)

Status values: TODO | IN PROGRESS | DONE

- Phase 00 (DONE): Baseline Verification + Repo Inventory
  - File: `phase-00-baseline-verification.md`

- Phase 01 (DONE): Release Spec + Manifest v2 + Signing + Anti-rollback
  - File: `phase-01-manifest-and-release-spec.md`

- Phase 02 (DONE): Distribution Repo + CI (stable/beta/nightly) + Pages Demos
  - File: `phase-02-distribution-repo-ci.md`

- Phase 02b (DONE): Maintainer Release Command (ms release publish)
  - File: `phase-02b-maintainer-release-command.md`

- Phase 02c (IN PROGRESS): Distribution - Full Assets + Bundle Layout Fix + Asset Reuse
  - File: `phase-02c-distribution-full-assets-and-asset-reuse.md`

- Phase 02d (DONE): OpenControl SDK Lock (Firmware Dependency BOM)
  - File: `phase-02d-open-control-sdk-lock.md`

- Phase 02e (IN PROGRESS): ms release --auto (strict)
  - File: `phase-02e-ms-release-auto-strict.md`

- Phase 03 (DONE): oc-bridge Upstream: Service Name Config + Linux Desktop Toggle
  - File: `phase-03-oc-bridge-service-names.md`

- Phase 04 (IN PROGRESS): ms-manager Foundation (Tauri+Svelte) + Fetch/Verify/Cache
  - File: `phase-04-ms-manager-foundation.md`

- Phase 05 (TODO): Transaction Engine (Updater/Helper) + Atomic current/ Swap + Rollback
  - File: `phase-05-transaction-engine.md`

- Phase 06 (TODO): End-user Features: Bridge Service, Bitwig Extension, Firmware Flash, Diagnostics
  - File: `phase-06-end-user-operations.md`

- Phase 07 (TODO): Stable Bootstrap Installer + Shortcuts + PATH
  - File: `phase-07-bootstrap-installer.md`

- Phase 08 (TODO): End-to-end Validation + First Public Release
  - File: `phase-08-e2e-and-first-release.md`

## Phase Dependencies (important)

- Phase 02b is a prerequisite for Phase 03+.
  - Rationale: publishing must be repeatable and maintainer-safe before we change upstream services.

- Phase 03 is a prerequisite for Phases 05/06/07.
  - Rationale: atomic `current/` upgrades and bridge lifecycle management require a stable service name and a stable service exec path (not a versioned `current_exe()` result).

- Phase 02c is a prerequisite for Phases 05/06/07/08.
  - Rationale: without a correct bundle layout and a stable asset/reuse contract, the transaction engine and end-user ops would be built on ambiguous assumptions.

- Phase 02d is strongly recommended before Phase 08.
  - Rationale: it reduces dependency drift and makes releases more reproducible and maintainable as profiles/DAWs grow.

## Notes (ongoing)

- Keep the distribution repo as the single end-user truth. ms-dev-env remains dev-only.
- Avoid “hidden” compatibility assumptions: encode them in the release spec + manifest.
- Prefer one canonical CI workflow per repo named `CI` (or similar) to simplify nightly selection.
