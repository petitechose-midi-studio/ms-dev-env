# Phase 07a: ms-manager App Updates (Tauri Updater) - Stable-only, Silent Badge

Status: TODO

## Goal

Ship a clean end-user story for updating **ms-manager itself**:

- First install: user downloads the platform installer from the latest stable `ms-manager` release.
- Ongoing: ms-manager checks for app updates silently and shows a small in-app badge when an update is available.
- User-driven install: no auto-install; user clicks to update.

Important: this phase is **only** about updating the GUI app (ms-manager). Runtime/content updates
(loader/bridge/firmware bundles) remain managed via the signed `distribution` manifest.

## Decisions (locked)

- App updates are **stable-only** for now.
- UX is **silent + badge** (no modal on launch, no notifications by default).
- No PATH changes or CLI exposure for end users.
- Signing scope (for now): **Tauri updater signing only** (no macOS notarization, no Windows code signing yet).

## User Model (end-user)

1) Download and install ms-manager

- Windows: `ms-manager-setup.exe` (NSIS, per-user).
- macOS: `.dmg` (drag-and-drop).
- Linux: start with AppImage (user-level), and later consider `.deb`/`.rpm`.

2) Use ms-manager to install/update MIDI Studio runtime

- The user selects the runtime channel (stable/beta/nightly) inside ms-manager.
- ms-manager resolves + verifies the signed `distribution` manifest and installs bundles.

3) Update ms-manager (the app)

- ms-manager checks for app updates in the background.
- When a newer version exists, a small badge appears in the UI.
- User clicks to install the update.

## Implementation (ms-manager repo)

### 1) Add Tauri Updater

- Add Rust plugin dependency: `tauri-plugin-updater`.
- Add JS guest bindings: `@tauri-apps/plugin-updater`.
- Enable updater artifacts:
  - `ms-manager/src-tauri/tauri.conf.json`:
    - `bundle.createUpdaterArtifacts = true`
- Configure the updater endpoint (stable-only):
  - `plugins.updater.endpoints = ["https://github.com/petitechose-midi-studio/ms-manager/releases/latest/download/latest.json"]`
- Embed the updater public key:
  - `plugins.updater.pubkey = "..."`
- Windows ergonomics:
  - `plugins.updater.windows.installMode = "passive"`

Capabilities:

- `ms-manager/src-tauri/capabilities/default.json` must include `updater:default`.

Backend initialization:

- `ms-manager/src-tauri/src/lib.rs`: initialize the updater plugin during app setup.

### 2) Add minimal update API surface (recommended)

Do not let the frontend call updater APIs directly.
Expose two Tauri commands from Rust instead:

- `app_update_check` -> returns `{ available, version, notes?, pub_date? }`.
- `app_update_install` -> downloads + installs the pending update.

Rationale:

- Centralizes policy (block update during flash/install/relocate).
- Allows best-effort shutdown of supervised daemons before installing.
- Keeps the security capability surface small.

### 3) UX: silent + badge

Where:

- Add a small badge in the header area (or a dedicated "App" badge next to the platform badge).

Behavior:

- On UI boot (after initial status load), trigger `app_update_check` async.
- If update exists: set `updateAvailable=true` and display a badge.
- Provide one action: "Update ms-manager".
  - If busy (flashing/installing/relocating): disable the button and show a short hint.
  - Before install: stop/kill oc-bridge daemons best-effort.
  - Run install.
  - On Windows: app will exit during install (expected).

Do not:

- Do not auto-install.
- Do not interrupt first-run flows.

## Key Management (Tauri updater signing)

One-time setup:

- Generate keys using Tauri CLI (private key must be kept forever):
  - `npm run tauri signer generate -- -w ~/.tauri/ms-manager.key`
- Store:
  - private key: secure vault (1Password, etc.)
  - public key: committed in `tauri.conf.json`

Repo secrets (GitHub Actions):

- `TAURI_SIGNING_PRIVATE_KEY` (path or full content)
- optional: `TAURI_SIGNING_PRIVATE_KEY_PASSWORD`

Risk:

- If the private key is lost, existing users cannot receive future in-app updates.

## Release Pipeline (ms-manager repo)

Current state:

- `ms-manager/.github/workflows/ci.yml` builds with `--no-bundle`.

Add a dedicated release workflow:

- File: `ms-manager/.github/workflows/release.yml`
- Trigger: git tag `vX.Y.Z` (stable)
- Build matrix:
  - `windows-latest` (NSIS)
  - `ubuntu-latest` (AppImage)
  - `macos-13` (x86_64) and `macos-14` (arm64) recommended
- Output:
  - installers/bundles
  - updater signatures (`.sig`)
  - a static update JSON (`latest.json`) published as a release asset

Implementation options:

- Recommended: use `tauri-apps/tauri-action` to build + attach artifacts and generate the update JSON.
- Alternative: custom workflow that:
  - runs `npm run tauri build`
  - reads the produced `.sig` files
  - writes `latest.json`
  - creates a GitHub release and uploads assets

## Versioning Procedure (maintainer)

For each stable ms-manager release:

1) Bump version in:
   - `ms-manager/package.json`
   - `ms-manager/src-tauri/Cargo.toml`
   - `ms-manager/src-tauri/tauri.conf.json`
2) Commit the version bump.
3) Create and push tag: `vX.Y.Z`.
4) Watch `release.yml` until success.
5) Verify:
   - GitHub Release has installers + `latest.json`.
   - In-app update works from the previous version.

## Interactions with runtime updates (distribution)

Keep the separation strict:

- ms-manager app updates: via Tauri updater + `ms-manager` GitHub Releases.
- MIDI Studio runtime/content updates: via `petitechose-midi-studio/distribution` signed manifests.

Related maintainer procedures:

- `docs/memories/work/ms-user-release-workflow/phase-02b-maintainer-release-command.md`
- `docs/memories/work/ms-user-release-workflow/phase-02e-ms-release-auto-strict.md`

## Exit Criteria

- A stable `ms-manager` release exists with multi-platform installers and `latest.json`.
- ms-manager checks for app updates silently and shows a badge when available.
- User can update ms-manager via one click (with safe blocking when busy).
- No PATH modifications are performed.

## Tests

Manual (required):

- Install stable ms-manager version A.
- Publish stable ms-manager version B.
- Launch A, verify badge appears, click update.
- Verify ms-manager is now version B.
- Verify update is blocked while a firmware flash is running.

Notes:

- Without OS-level code signing/notarization, expect friction on Windows/macOS. This is accepted
  for now, but must be addressed before a wider public release.
