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
  - default install = latest stable bundle
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
  - JSON supports `--json-timestamps` and `--json-progress`.
  - Recent loader commits (baseline):
    - `eb56bc0` feat!: simplify JSON contract for list and target records
    - `a252634` feat: add operation summary JSON event

- `open-control/bridge` provides:
  - local control plane (`oc-bridge ctl pause|resume|status`)
  - Windows service install/uninstall (currently hard-coded service name)
  - Linux systemd user service install (currently hard-coded service name + installs a .desktop)
  - Note: Linux service install uses `current_exe()` path, which can resolve to a versioned path
    even when the binary is reached via a `current/` symlink. We must address this to keep
    service ExecStart stable across upgrades.

- `ms-dev-env` already has CI workflows that build and package artifacts (dev-oriented). We will not ship ms-dev-env to end users.

## Decisions (locked)

- Distribution uses a dedicated repo (GitHub Releases + Pages).
- Bundles are cohesive: end user selects a bundle tag (not per-component versions).
- Channels: stable/beta/nightly.
- Nightly selection: per repo, pick the latest commit with CI success; skip nightly if any repo lacks a green commit.
- macOS/Linux: user services when possible.
- Windows: admin allowed; service points to stable `current/`.
- oc-bridge remains agnostic; MIDI Studio requires service-name configurability to avoid collisions.
- ms-manager GUI: Tauri + Svelte.
- macOS/Linux symlinks: install to `/usr/local/bin` (sudo) for frictionless CLI usage.

## Phases (tracking)

Status values: TODO | IN PROGRESS | DONE

- Phase 00 (DONE): Baseline Verification + Repo Inventory
  - File: `phase-00-baseline-verification.md`

- Phase 01 (DONE): Release Spec + Manifest v2 + Signing + Anti-rollback
  - File: `phase-01-manifest-and-release-spec.md`

- Phase 02 (IN PROGRESS): Distribution Repo + CI (stable/beta/nightly) + Pages Demos
  - File: `phase-02-distribution-repo-ci.md`

- Phase 03 (TODO): oc-bridge Upstream: Service Name Config + Linux Desktop Toggle
  - File: `phase-03-oc-bridge-service-names.md`

- Phase 04 (TODO): ms-manager Foundation (Tauri+Svelte) + Fetch/Verify/Cache
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

- Phase 03 is a prerequisite for Phases 05/06/07.
  - Rationale: atomic `current/` upgrades and bridge lifecycle management require a stable service name and a stable service exec path (not a versioned `current_exe()` result).

## Notes (ongoing)

- Keep the distribution repo as the single end-user truth. ms-dev-env remains dev-only.
- Avoid “hidden” compatibility assumptions: encode them in the release spec + manifest.
- Prefer one canonical CI workflow per repo named `CI` (or similar) to simplify nightly selection.
