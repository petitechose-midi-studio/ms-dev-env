# Phase 07: Stable Bootstrap Installer + Shortcuts

Status: TODO

## Goal

Ship a stable bootstrap installer that:

- installs ms-manager (and ms-updater helper)
- creates desktop/start-menu/app shortcuts
- launches ms-manager for first-run install of the latest stable bundle

The bootstrap should change rarely.

Prerequisites:
- Phase 03 is complete so ms-manager can install/manage oc-bridge without collisions and with a stable exec path (`--service-name`, `--service-exec`, `--no-desktop-file`).

## Approach (recommended)

- Use Tauri bundler to build installers per platform.
- The installer ships a known ms-manager build; afterwards, ms-manager can self-update (user-driven).

App self-updates are tracked in:
- `docs/memories/work/ms-user-release-workflow/phase-07a-ms-manager-app-updates.md`

Platform specifics (v1):

- Windows 10+:
  - Ship NSIS `-setup.exe`.
  - WebView2: use `downloadBootstrapper` so WebView2 is installed if missing.
  - Fallback (offline / locked-down IT): document how to install WebView2 Runtime manually.
- macOS:
  - Ship DMG.
  - For good UX, plan signing + notarization (Gatekeeper).
- Linux:
  - Start with AppImage (user-level), and later consider `.deb`/`.rpm` if we want package-managed deps.
  - Supported matrix for v1 requires WebKitGTK 4.1 (see Phase 04).

## PATH / CLI

Decision (v1): do not modify PATH for end users.

Notes:

- GUI apps on macOS/Linux do not reliably inherit shell `$PATH`.
- ms-manager must not depend on `$PATH` to find bundled binaries.

## Exit Criteria

- Installers exist for Windows/macOS/Linux.
- First run installs latest stable bundle (selected channel defaults to stable).
  - Resolve latest stable via GitHub Releases API (and/or `releases/latest` when available).
- Shortcuts behave as expected.
- No PATH changes are performed.

## Tests

Manual (required):
- Fresh VM install for each OS
- Run bootstrap installer
- Confirm:
  - ms-manager launches
  - installs stable bundle
  - oc-bridge service works (installed under the MIDI Studio service name; points to `current/` exec path)
  - shortcuts work
