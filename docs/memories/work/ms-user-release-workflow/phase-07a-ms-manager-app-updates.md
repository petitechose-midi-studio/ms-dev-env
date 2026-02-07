# Phase 07a: ms-manager App Updates (Manual latest-release redirect)

Status: TODO

## Goal

Provide a clear and consistent app-update story for `ms-manager` itself:

- same behavior on Windows/macOS/Linux
- no in-app binary install
- user is redirected to GitHub latest release to download/install manually

Important: this phase is only about the GUI app binary (`ms-manager`).
Runtime/content updates (loader/bridge/firmware bundles) remain in-app via signed
distribution manifests.

## Locked policy

- App update mode: manual on all platforms.
- In-app UX: silent check + small badge is allowed.
- App update action: open
  `https://github.com/petitechose-midi-studio/ms-manager/releases/latest`.
- No Tauri updater install flow (`download_and_install`) in v1.
- No AppImage or NSIS in app releases.

Package targets for app releases:

- Windows: MSI (WiX)
- macOS: DMG
- Linux: DEB + RPM

## User model

1) Install `ms-manager` from GitHub Releases package for the platform.

2) Use `ms-manager` to manage MIDI Studio runtime/content updates in-app.

3) When a new app version exists:

- app can show an "update available" badge
- user clicks update action
- app opens `releases/latest`
- user downloads and installs package manually

## Implementation (ms-manager repo)

### 1) Remove app auto-installer behavior

Files (expected):

- `src-tauri/src/commands/app_update.rs`
- `src-tauri/src/lib.rs`
- `src/lib/state/dashboard.ts`
- `src/lib/screens/Dashboard.svelte`
- `src/lib/api/client.ts`
- `src/lib/api/types.ts`

Requirements:

- Remove in-app install command/path for app binary updates.
- Keep or add a check command that reports "update available" + target URL.
- UI button must open browser to latest release page.

### 2) Remove updater-specific build plumbing (if unused)

Files (expected):

- `src-tauri/Cargo.toml`
- `src-tauri/tauri.conf.json`

Requirements:

- Remove `tauri-plugin-updater` wiring if no longer required by app logic.
- Remove updater artifact requirements from release process (`latest.json`, updater signatures)
  for app binary delivery.

### 3) Keep package outputs native and explicit

File:

- `src-tauri/tauri.conf.json`

Requirements:

- Targets are exactly: `msi`, `dmg`, `deb`, `rpm`.
- Explicitly remove: `appimage`, `nsis`.

## Release pipeline implications

`ms-manager` candidate/release workflows must:

- promote native package artifacts only (`msi`, `dmg`, `deb`, `rpm`)
- avoid updater-specific promote steps (for example `latest.json` rewrites)
- keep provenance via `rc-<source_sha>` candidate assets

This is coordinated with:

- `docs/memories/work/ms-user-release-workflow/phase-02g-unified-release-control-plane.md`
- `docs/memories/work/ms-user-release-workflow/phase-02h-option1-single-heavy-build.md`
- `docs/memories/work/ms-user-release-workflow/phase-02gh-execution-plan-manual-app-updates.md`

## Exit criteria

- App update action is manual redirect to GitHub latest release page.
- No in-app app-binary auto-install code path remains.
- App release assets include MSI/DMG/DEB/RPM only.
- Runtime/content in-app update flows remain unchanged and working.

## Tests

Manual (required):

1) Install app version A.
2) Publish app version B.
3) Launch A and confirm:
   - badge/check reports new app version (if enabled)
   - clicking update opens browser to `releases/latest`
   - no in-app install/restart is triggered
4) Install version B manually and confirm app version updates correctly.
