# Phase 04: ms-manager Foundation (Tauri + Svelte) - Fetch/Verify/Cache

Status: IN PROGRESS

## Goal

Create `ms-manager` as the end-user GUI that:

- defaults to the `stable` channel on first launch
- persists the selected channel (updates are only received from the selected channel)
- installs the latest release of the selected channel ("latest")
- supports advanced tag selection within the selected channel (rollback / pin)
- downloads with caching
- verifies manifest signature and asset sha256
- stages installs into `versions/<tag>/` and switches `current/`

## Intermediate Step (Maintainability Contract)

Before implementing download/cache/extract/install flows, refactor the foundation to keep the
codebase maintainable long-term (open-source friendly):

- Source of truth: persisted settings live in the backend (not `localStorage`).
- Split `src-tauri/src/lib.rs` into cohesive modules (commands/services/state).
- Define a stable IPC contract:
  - typed responses
  - structured errors (`code`, `message`, optional `details`)
- Centralize constants and pure helpers into `ms-manager-core` (DRY across future sidecars).
- Prepare for Phase 05 (transaction engine): keep a strict plan/apply separation.

This phase focuses on the foundation (network + storage + verification + minimal UI).

## Repo Setup

- New public repo: `petitechose-midi-studio/ms-manager`
- Stack:
  - Tauri (Rust backend)
  - Svelte (lightweight UI)

## Core Architecture

Backend (Rust):
- `dist_client`:
  - resolve the latest tag for the selected channel via GitHub Releases API
    - stable: prefer `releases/latest` when it exists; must handle 404 gracefully
  - download `manifest.json` + `manifest.json.sig` from `releases/download/<tag>/...`
  - list available releases (filtered by channel) for rollback
  - download assets (with caching)
  - rate-limit/NAT resilience:
    - stable path should not require `api.github.com`
    - cache release listing/tag resolution (TTL)
    - fallback to the Releases Atom feed when the API is unavailable/rate-limited
    - never block install/update on fetching release notes (load lazily)
- `verify`: Ed25519 signature verify + sha256 verify
- `storage`: install roots, cache, versions/current
- `ops`: install/update transactions (Phase 05 will finalize)

Frontend (Svelte):
- Default mode:
  - Channel selector (exclusive): stable | beta | nightly
  - Default selection on first launch: stable
  - Persist last selected channel
  - Primary action: “Install/Update latest” (for the selected channel)
  - If stable has no published releases yet: show an empty state and offer switching to beta/nightly (no auto-switch)
- Advanced mode:
  - select a tag (within the selected channel)
  - list tags via GitHub Releases API (fallback: installed local versions)
  - install selected tag (with explicit confirmation when it would downgrade)

## Execution Plan (ordered)

1) Cleanup (prerequisite)
- Remove legacy channel pointers from the distribution repo (delete `channels/`, channel-pointer schema, helper script).
- Simplify Actions workflows (publish/nightly/pages) accordingly.
- Publish schemas on Pages (`/schemas/*.json`).

2) Repo bootstrap
- Create `petitechose-midi-studio/ms-manager` (Tauri + Svelte) + minimal CI.

3) Verification core
- Implement manifest signature verification (Ed25519) + asset sha256 verification + test fixtures.

4) "Latest" resolution per channel
- stable: `releases/latest` when available + graceful 404.
- beta/nightly: Releases API with caching + Atom fallback.

5) Download + cache + extract
- Atomic-ish downloads (tmp + rename), cache reuse, extract full bundle, ensure executables on macOS/Linux.

6) Install layout
- Install into `versions/<tag>/`, switch `current/`, persist app state (selected channel + installed tag).

7) Minimal UX
- Channel radio (exclusive), stable default on first launch, persist selection, empty state when stable is unavailable.

8) Progressive tests
- Local fake distribution server.
- Real-tag smoke against existing beta/nightly releases in the distribution repo.

## Install Roots (v1)

- Windows:
  - App installed via installer.
  - Payload root: `C:\ProgramData\MIDI Studio\`.
- macOS:
  - Payload root: `~/Library/Application Support/MIDI Studio/`.
- Linux:
  - Payload root: `~/.local/share/midi-studio/`.

Within payload root:
- `versions/<tag>/...`
- `current -> versions/<tag>` (symlink/junction)
- `state/state.json`
- `logs/`

## Platform Support + Distribution (v1)

This phase focuses on the app foundation, but we lock down platform assumptions now to avoid
accidental compatibility drift.

Supported targets (explicit):

- Windows: Windows 10+ (x86_64).
- macOS: macOS 13+ (targeting ~95% user coverage in 2026).
- Linux (WebKitGTK 4.1 required):
  - Debian: 13+ (stable).
  - Ubuntu: 24.04+.
  - Fedora: current stable.
  - RHEL-family: 10+ (or equivalent, with WebKitGTK 4.1 available).
  - Not supported: RHEL 9.

WebView prerequisites:

- Windows:
  - Uses Edge WebView2 Evergreen runtime.
  - Installer strategy (Phase 07): `downloadBootstrapper` to install WebView2 if missing.
  - If the installer cannot download (offline / locked-down IT): instruct users to pre-install
    WebView2 Runtime, then re-run the installer.
- macOS:
  - WebKit is built-in (no separate runtime install).
- Linux:
  - `.deb` / `.rpm` packages declare dependencies so the package manager installs WebKitGTK + GTK.

Packaging plan (Phase 07 will ship the bootstrap installers):

- Windows: NSIS `-setup.exe` via Tauri bundler + WebView2 bootstrapper.
- macOS: DMG (and later: signed + notarized for good Gatekeeper UX).
- Linux:
  - Debian/Ubuntu: `.deb` (install with `apt install ./file.deb`, not `dpkg -i`).
  - Fedora/RHEL: `.rpm` (install with `dnf install ./file.rpm`, not `rpm -i`).

Build constraints:

- Linux binaries must be built on the oldest base system we intend to support (glibc). For our
  chosen matrix, build `.deb` in an Ubuntu 24.04 environment and `.rpm` in a RHEL 10 / Fedora
  environment aligned with the target.
- GUI apps on macOS/Linux do not reliably inherit shell `$PATH`. Prefer absolute paths and
  `current/`-based locations; do not rely on `.bashrc` / `.zshrc`.

## Exit Criteria

- App runs on all target OS.
- Can resolve and fetch the latest manifest for the selected channel.
  - Stable must handle the "no stable yet" case gracefully.
- Verifies manifest signature and asset sha256.
- Stores downloaded assets in a cache and reuses it.

## Notes (recorded)

Public keys (Ed25519, base64, 32 bytes):
- stable/release: `2rHtM99leFGTpjZ8fZHNCdGXlEKmAw6hEyaat1uGO3M=`
- nightly: `voOksaS+NoUkEy9c8YunbTwPnb1dlXCyEJ9Yy07233A=`

## Tests

Local (fast):
- Rust unit tests:
  - manifest signature verification (test key)
  - sha256 verification
  - path resolution per OS

Local (full):
- `cargo test`
- Tauri dev run:
  - Install simulation using a local fake distribution server.
  - Integration smoke against real tags (beta/nightly) in `petitechose-midi-studio/distribution`.

## Progress (recorded)

- Distribution cleanup: channel pointers removed (merged): https://github.com/petitechose-midi-studio/distribution/pull/22
- `ms-manager` repo created: https://github.com/petitechose-midi-studio/ms-manager
- Foundation implemented:
  - channel selector (exclusive, persisted in UI)
  - resolve latest manifest per channel (stable uses `releases/latest` with graceful 404)
  - signature verification (Ed25519) + manifest schema parsing (v2)

- Intermediate maintainability step (in progress):
  - backend settings store (single source of truth for selected channel)
  - structured IPC errors + typed API wrapper (TS)
  - split `src-tauri` into commands/services/state modules
