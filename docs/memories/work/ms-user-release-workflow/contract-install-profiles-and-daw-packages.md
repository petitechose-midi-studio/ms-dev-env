# Contract: Install Profiles (install_sets) + Multi-DAW Integrations

Status: LOCKED
Date: 2026-02-03

## Context

We ship a single end-user app (`ms-manager`) that installs and updates MIDI Studio.

Key constraints and goals:
- Users can work standalone (no DAW) or with a DAW integration.
- Device firmware storage is constrained: we must assume only one DAW integration can be installed at a time.
- The update system must be safe and deterministic:
  - signed manifest (Ed25519)
  - sha256 per asset
  - no implicit combinations
- UX must stay straightforward; maintainability is more important than maximizing flexibility.

## Terms

- Channel: `stable` | `beta` | `nightly`.
- Tag: a GitHub Release tag (e.g. `v0.1.0`, `v0.1.0-beta.2`, `nightly-YYYY-MM-DD`).
- Manifest: `manifest.json` v2 + `manifest.json.sig` (Ed25519 detached signature).
- Asset: a file referenced by the manifest (bundle, firmware, DAW package).
- Install set: an entry in `install_sets[]` in the manifest.

## Locked v1 decisions

- Supported profiles: `default` and `bitwig`.
- Firmware model:
  - `default` profile ships a standalone-only firmware (core).
  - `bitwig` profile ships a firmware that includes standalone + Bitwig integration.
- Tags are cohesive: every tag contains all supported profiles.
- Asset reuse is supported via `assets[].url` (same-channel only).
  - stable/beta are published as self-contained tags (copy reuse).
  - nightly may use `assets[].url` to reference prior nightly assets.

## The core idea: install_sets == profiles

We treat `install_sets` as explicit installation profiles.

- A single tag can expose multiple profiles.
- `install_set.id` is the profile id.
- `default` is mandatory in every manifest and represents the Standalone profile.
- Additional profile ids are DAW-specific and stable over time:
  - examples: `bitwig`, `ableton`, `flstudio`, `reaper`, ...

User mental model:
1) Choose a channel.
2) Choose a profile.
3) Install "latest" (or select a tag in Advanced).

Runtime behavior:
- Standalone behavior is the baseline.
- If a DAW profile is installed, the controller can still be used standalone when the DAW is not running.

## Distribution contract (per tag)

The signed manifest is the single source of truth.

### Assets by kind

We publish multiple assets and assemble them via `install_sets`:

- `bundle` (OS/arch): host tools (oc-bridge + midi-studio-loader + config).
- `firmware` (platform-independent): one firmware per profile.
- DAW integration packages (platform-independent): one package per profile.

Notes:
- The current schema already includes `firmware` and `bitwig-extension` kinds.
- v1 uses a direct Bitwig asset (`midi_studio.bwextension`). Future DAWs may require a more generic packaging approach.

### install_sets selection rule

Given:
- selected profile id (e.g. `default`, `bitwig`)
- current platform (`os`, `arch`)

We select the install set where:
- `install_set.id == <profile_id>`
- `install_set.os == current_os`
- `install_set.arch == current_arch`

That install set lists the asset ids to download/install.

## Safe-by-default rules

- A tag must be self-contained: the manifest must reference all needed assets for all profiles.
- Default update path must never auto-downgrade.
- Downgrade/pin is allowed only in Advanced UI with explicit confirmation.
- Avoid relying on Nightly releases as long-term base artifacts.

## Asset reuse (LOCKED)

We allow a tag to reuse unchanged assets from an earlier tag.

Implementation:

- stable/beta: copy reuse (self-contained)
  - unchanged assets are copied from an earlier tag and re-uploaded to the current tag
  - `assets[].url` is typically omitted
- nightly: URL reuse (quota-efficient)
  - set `manifest.assets[].url` to point at an existing release asset URL
  - the new manifest still includes `size` + `sha256` so verification remains local

Policy:

- Reuse is same-channel only (stable->stable, beta->beta, nightly->nightly).
- stable/beta must never reference nightly assets.
- Do not rely on nightly artifacts as long-term dependencies.

## Installing DAW resources: keep ms-manager generic

Principle: `ms-manager` should not embed per-DAW installation procedures.

Recommendation:
- Each DAW integration is shipped as a package (zip) plus a small declarative descriptor
  (e.g. `integration.json`) describing allowed file operations.
- A dedicated tool (preferably `midi-studio-loader`, already in the bundle) executes the descriptor:
  - install / uninstall / detect
  - emits progress + machine-readable summaries

Benefits:
- Adds new DAWs without growing `ms-manager` into a pile of special cases.
- Keeps execution safe (no arbitrary shell scripts).
- Reuses the same progress/event patterns already used by loader operations.

## Pending decisions (post-v1)

- Multi-DAW scaling strategy:
  - likely add a generic `daw-package` kind in schemas.
  - keep ms-manager generic by installing “DAW packages” declaratively.
