# Contract: Install Profiles (install_sets) + Multi-DAW Integrations

Status: DRAFT (aligned in conversation)
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
- For multi-DAW scaling, prefer a generic kind such as `daw-package` (future schema extension),
  instead of multiplying kinds (`ableton-extension`, `flstudio-extension`, ...).

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

## Future: avoid rebuilding/reuploading everything (asset reuse)

Short term: republishing full bundles is acceptable.

Long term: to support fast-moving DAWs (e.g. FL Studio) without rebuilding/reuploading all OS bundles:
- We still publish a new tag (keeps UX simple: one version == one tag).
- We allow a tag to reuse unchanged assets from earlier tags.

Implementation approach (future):
- Manifest assets may set `asset.url` to point at an existing release asset.
- The new manifest still includes `size` + `sha256` so verification remains local.

Operational constraint:
- Only reuse assets from stable/beta tags we do not delete.
- Do not reuse nightly artifacts for long-term linking.

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

## Pending decisions to lock

1) Tag composition:
- Preferred: each tag contains all supported profiles (default + all DAWs).

2) DAW integration packaging:
- Confirm the "package + declarative descriptor executed by midi-studio-loader" approach.
