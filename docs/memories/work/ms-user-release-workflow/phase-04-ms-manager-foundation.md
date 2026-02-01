# Phase 04: ms-manager Foundation (Tauri + Svelte) - Fetch/Verify/Cache

Status: TODO

## Goal

Create `ms-manager` as the end-user GUI that:

- installs latest stable bundle by default
- supports advanced channel + tag selection
- downloads with caching
- verifies manifest signature and asset sha256
- stages installs into `versions/<tag>/` and switches `current/`

This phase focuses on the foundation (network + storage + verification + minimal UI).

## Repo Setup

- New public repo: `petitechose-midi-studio/ms-manager`
- Stack:
  - Tauri (Rust backend)
  - Svelte (lightweight UI)

## Core Architecture

Backend (Rust):
- `dist_client`:
  - fetch latest stable manifest via GitHub Releases `latest` endpoint
  - list available releases for rollback via GitHub Releases API
  - download assets (with caching)
- `verify`: Ed25519 signature verify + sha256 verify
- `storage`: install roots, cache, versions/current
- `ops`: install/update transactions (Phase 05 will finalize)

Frontend (Svelte):
- Simple mode: one button “Install latest stable”
- Advanced mode:
  - select channel
  - list tags via GitHub Releases API (fallback: installed local versions)
  - install selected tag

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
- Can fetch latest stable manifest from:
  - `https://github.com/petitechose-midi-studio/distribution/releases/latest/download/manifest.json`
  - `https://github.com/petitechose-midi-studio/distribution/releases/latest/download/manifest.json.sig`
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
- Tauri dev run + install simulation using local fake distribution server.
