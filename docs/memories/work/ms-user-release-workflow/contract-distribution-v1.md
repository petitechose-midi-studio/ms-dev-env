# Contract: Distribution v1 (Assets, Bundle Layout, Asset Reuse)

Status: LOCKED
Date: 2026-02-03

## Goal

Define a single, unambiguous end-user distribution contract that is:

- safe (signed manifest + sha256 per asset)
- deterministic (tag -> pinned SHAs -> assets)
- simple to operate (stable/beta/nightly)
- efficient (reuse unchanged assets without rebuilding/reuploading)

This contract is the prerequisite for a robust transaction engine (`ms-updater`) and reliable end-user operations.

## Source Of Truth

End-user feed is **only**:

- GitHub Releases in `petitechose-midi-studio/distribution`

Notes:

- `ms-dev-env` is dev-only. It must not be confused with the end-user distribution feed.

Scope:

- This contract covers the **payload** installed under `versions/<tag>/` and pointed to by `current/`.
- `ms-manager` (GUI) and `ms-updater` (apply helper) are shipped by the bootstrap installer (Phase 07) and are not part of the manifest v2 schema.

## Terms

- Channel: `stable` | `beta` | `nightly`.
- Tag: a GitHub Release tag.
- Release spec: `release-specs/<tag>.json` (inputs, schema=1).
- Manifest: `manifest.json` (outputs, schema=2) + `manifest.json.sig`.
- Profile: an installation profile == `install_set.id`.

## Non-Negotiable Invariants

- `manifest.json` is always verified:
  - signature (Ed25519)
  - sha256 for every downloaded asset
- The manifest is the only source of truth for what to install.
- A tag is cohesive: it supports the expected profiles and platforms (no hidden “mix and match”).
- Default update path must never auto-downgrade (client-enforced).

## Profiles (v1)

We ship two firmware lines:

- `default` = standalone only (core firmware)
- `bitwig` = standalone + Bitwig extension (firmware extension)

Rules:

- Exactly one profile is active on the controller at a time.
- A release tag must contain *all* supported profiles (v1: `default` + `bitwig`).

## Asset Kinds (schema)

The `distribution` schemas currently support:

- `bundle` (OS/arch)
- `firmware` (platform-independent)
- `bitwig-extension` (platform-independent)

## Asset Naming (v1)

Bundles (per OS/arch):

- `midi-studio-windows-x86_64-bundle.zip`
- `midi-studio-macos-x86_64-bundle.zip`
- `midi-studio-macos-arm64-bundle.zip`
- `midi-studio-linux-x86_64-bundle.zip`

Firmware (profile-scoped, platform-independent):

- `midi-studio-default-firmware.hex`
- `midi-studio-bitwig-firmware.hex`

Bitwig extension (platform-independent):

- `midi_studio.bwextension`

## Bundle Zip Layout (v1)

The oc-bridge config **must be discoverable by oc-bridge**.

Constraint (oc-bridge today): it looks for `config.toml` / `config/**` **next to the executable**.

Therefore the bundle layout is:

```
<bundle>.zip
  bin/
    oc-bridge[.exe]
    midi-studio-loader[.exe]
    config/
      default.toml
      devices/
        teensy.toml
```

Notes:

- The previous layout `bridge/config/**` is invalid for oc-bridge config discovery and must not be used.

## install_sets Mapping (v1)

For each supported platform (os+arch), we publish:

- `install_set.id=default`: `assets = [bundle_<os>_<arch>, firmware_default]`
- `install_set.id=bitwig`: `assets = [bundle_<os>_<arch>, firmware_bitwig, bitwig_extension]`

Where:

- bundle asset id is platform-scoped (`bundle-windows-x86_64`, ...)
- firmware/extension asset ids are platform-independent (`firmware-default`, `firmware-bitwig`, `bitwig-extension`)

## Asset Reuse (LOCKED)

We support “reuse unchanged assets” to avoid rebuilding/reuploading everything when only some repos change.

Mechanism:

- A new tag may reuse an earlier tag’s assets by setting `assets[].url`.
- The new manifest is still signed and still contains `sha256` + `size` for every asset.

URL format (GitHub Releases assets):

- `https://github.com/petitechose-midi-studio/distribution/releases/download/<tag>/<filename>`

Policy:

- Reuse is **same-channel only**:
  - stable reuses stable
  - beta reuses beta
  - nightly reuses nightly
- stable/beta must never reference nightly assets.
- Do not treat nightly assets as long-term stable dependencies.

Operational note:

- A release tag is considered “complete” if the **manifest** contains all required assets.
- The GitHub Release page for that tag may upload only the changed assets + `manifest.json(.sig)`.
  Reused assets may live on earlier tags and be fetched via `assets[].url`.

Client rule (ms-manager):

- If `asset.url` is present: download from it.
- Else: download the asset from the current tag’s release.
- Always verify sha256 after download.

## Reuse Decision Model (v1)

We decide “build vs reuse” per asset group.

Asset groups and repo dependencies:

- `bundle-*`:
  - depends on `loader@sha` and `oc-bridge@sha`
- `firmware-default`:
  - depends on `core@sha`
- `firmware-bitwig`:
  - depends on `core@sha` and `plugin-bitwig@sha` (Bitwig firmware includes the standalone base)
- `bitwig-extension`:
  - depends on `plugin-bitwig@sha`

Recipe fingerprint (guardrail):

- Reuse is allowed only if packaging/build recipes are unchanged between previous tag and current HEAD.
- The fingerprint is computed from versioned files in the `distribution` repo (example set):
  - `scripts/package_bundle.py`
  - `.github/workflows/publish.yml`
  - `.github/workflows/nightly.yml`
  - `tools/ms-dist-manifest/Cargo.lock`

If fingerprint differs: force rebuild for all assets (no reuse).

## Implementation Notes

- The reuse planner must verify the previous manifest signature before copying `sha256/size` into the new manifest.
- A tag may publish only changed assets + the new manifest + signature. Reused assets are not reuploaded.
