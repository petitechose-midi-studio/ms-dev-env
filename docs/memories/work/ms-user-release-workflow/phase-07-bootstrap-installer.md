# Phase 07: Stable Bootstrap Installer + Shortcuts + PATH

Status: TODO

## Goal

Ship a stable bootstrap installer that:

- installs ms-manager (and ms-updater helper)
- creates desktop/start-menu/app shortcuts
- optionally installs CLI symlinks into `/usr/local/bin` (macOS/Linux)
- launches ms-manager for first-run install of the latest stable bundle

The bootstrap should change rarely.

Prerequisites:
- Phase 03 is complete so ms-manager can install/manage oc-bridge without collisions and with a stable exec path (`--service-name`, `--service-exec`, `--no-desktop-file`).

## Approach (recommended)

- Use Tauri bundler to build installers per platform.
- The installer ships a known ms-manager build, but ms-manager updates itself on first run.

Platform specifics (v1):

- Windows 10+:
  - Ship NSIS `-setup.exe`.
  - WebView2: use `downloadBootstrapper` so WebView2 is installed if missing.
  - Fallback (offline / locked-down IT): document how to install WebView2 Runtime manually.
- macOS:
  - Ship DMG.
  - For good UX, plan signing + notarization (Gatekeeper).
- Linux:
  - Debian/Ubuntu: ship `.deb` and instruct users to install via `apt install ./...deb`.
  - Fedora/RHEL: ship `.rpm` and instruct users to install via `dnf install ./...rpm`.
  - Supported matrix for v1 requires WebKitGTK 4.1 (see Phase 04).

## PATH / CLI

Goal: users can run:
- `ms-manager`
- `oc-bridge`
- `midi-studio-loader`

macOS/Linux:
- create symlinks to `current/...` in `/usr/local/bin` (sudo).

Note: GUI apps on macOS/Linux do not reliably inherit shell `$PATH`.
ms-manager must not depend on `$PATH` to find bundled binaries.

Windows:
- optional: add `current/bin` directory to PATH (machine-wide, admin).

## Exit Criteria

- Installers exist for Windows/macOS/Linux.
- First run installs latest stable bundle via distribution channel pointer.
- Shortcuts and PATH behave as expected.

## Tests

Manual (required):
- Fresh VM install for each OS
- Run bootstrap installer
- Confirm:
  - ms-manager launches
  - installs stable bundle
  - oc-bridge service works (installed under the MIDI Studio service name; points to `current/` exec path)
  - PATH and shortcuts work
