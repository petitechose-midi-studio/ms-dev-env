# Phase 02: Distribution Repo + CI (stable/beta/nightly) + Pages Demos

Status: DONE

## Goal

Create the dedicated distribution repo and implement:

- Stable/beta publish workflow (manual / workflow_dispatch)
- Nightly workflow (scheduled, skip if not fully green)
- GitHub Pages demos (per channel)
- Pages site (channels + demo placeholders)

Important constraint (today):
- Org policy prevents GitHub Actions from creating PRs.
- This repo requires PRs for changes to `main`.
- Therefore `channels/*.json` cannot be auto-updated by CI.

Default install strategy (v1):
- Stable update uses GitHub Releases `latest` assets.
- Advanced selection / rollback lists releases via GitHub Releases API.

## Repo Layout (recommended)

- `channels/`
  - `stable.json`
  - `beta.json`
  - `nightly.json`
  - optional index files can be added later, but v1 uses GitHub Releases API for listing

- `schemas/` (from Phase 01)

- `scripts/`
  - `select_latest_green.py` (nightly selection)
  - `package_bundle.py` (bundle zip)
  - `update_channel_pointer.py` (manual helper)

- `.github/workflows/`
  - `ci.yml`
  - `publish.yml` (stable/beta)
  - `nightly.yml` (scheduled)
  - `pages.yml`

## Workflows

### A) publish.yml (stable/beta)

Inputs:
- `channel`: stable|beta
- `tag`: vX.Y.Z or vX.Y.Z-beta.N
- `spec_path`: path to `release-specs/<tag>.json` in the distribution repo

Steps (high-level):
1) Checkout distribution repo.
2) Checkout each pinned repo at exact SHA.
3) Build matrix (OS/arch):
   - `midi-studio-loader`
   - `oc-bridge` (+ config folder)
   - (later) `ms-manager` (Tauri)
   - (later) firmware bundles + Bitwig extension
4) Package zips with deterministic names.
5) Generate + sign `manifest.json`.
6) Create GitHub Release + upload all assets.
7) Emit channel pointer URLs (manual update via PR).
8) Pages site deploy (channels + placeholder demos).

### B) nightly.yml

Schedule: daily.

Selection rules:
- For each required repo, query GitHub API for the latest successful `CI` workflow run on `main`.
- If any repo has no successful run: SKIP nightly.

Then run the same pipeline as publish.yml with:
- channel=nightly
- tag=`nightly-YYYY-MM-DD`
- prerelease=true

If the distribution build fails: publish nothing.

Implementation detail (recommended):
- Encode the canonical workflow file name in the release spec (e.g. `.github/workflows/ci.yml`).
- Query (REST API):
  - `GET /repos/{owner}/{repo}/actions/workflows/{workflow_file}/runs?branch=main&event=push&status=success&per_page=1`
  - Use the first run's `head_sha`.
- Guardrails:
  - Ignore PR-only runs.
  - Require `status=success`.
  - If the endpoint returns empty: treat as missing => skip nightly.

## Deterministic asset naming

Use stable filenames, similar to current `ms/services/dist.py` naming:

- `midi-studio-<os>-<arch>-bundle.zip` (contains manager + loader + oc-bridge + config)
- v1 bundle contains: loader + oc-bridge + config
- (later) add: ms-manager + firmware + Bitwig extension
- `manifest.json` + `manifest.json.sig`

Note: keep the “bundle” structure friendly for `current/` layout.

## Pages demos

Publish to GitHub Pages:
- `/demos/stable/`
- `/demos/beta/`
- `/demos/nightly/`

The demos are built in CI but are not included in the installed bundle.

## Exit Criteria

- Distribution repo exists and is public.
- publish workflow produces a release with signed manifest and correct assets.
- nightly workflow skips if any repo lacks green CI.
- pages deploy works.
- Stable update uses `releases/latest/download/manifest.json` + `.sig`.
- Release listing for rollback is possible via GitHub Releases API.

## Progress (recorded)

Repo created:
- `petitechose-midi-studio/distribution`

Baseline security applied:
- `SECURITY.md` documents key handling and hardening.
- `.github/CODEOWNERS` added for critical paths.
- `main` branch protection enabled (PR required; no force-push/deletion; conversation resolution).
  - Note: approvals/code-owner review are recommended, but not enforced today (single-maintainer constraint).
- GitHub Actions environments created:
  - `release` (required reviewer: `petitechose-audio`)
  - `nightly` (no reviewers)

Baseline CI:
- `.github/workflows/ci.yml` runs `cargo test` for the distribution repo.

Workflows implemented (initial):
- `publish.yml` (manual stable/beta): builds loader + oc-bridge bundles, generates + signs manifest, publishes a GitHub Release.
- `nightly.yml` (scheduled): selects latest green commits, builds bundles, signs with nightly key, publishes prerelease.

Smoke inputs:

- Use the maintainer command (Phase 02b):
  - `ms release publish --channel beta`

Smoke result:

- Publish workflow succeeded for beta releases (`v0.0.1-beta.1`, `v0.0.1-beta.2`).
- Nightly workflow is publishing prereleases (e.g. `nightly-2026-02-01`).

Issues found + fixed during smoke:
- Cargo workspace conflict when checking out repos under `src/`.
  - Fix: `distribution/Cargo.toml` excludes `src/loader`, `src/oc-bridge`, `src/ms-manager`.
- Linux build failed on missing `libudev`.
  - Fix: install `libudev-dev` + `libusb-1.0-0-dev` on Ubuntu runners.
- macOS runner label deprecation.
  - Fix: switch to `macos-15-intel` (x86_64) and `macos-latest` (arm64).

- Compact bundle binaries:
  - Build loader with `--no-default-features --features cli`.
  - Apply size-focused profile settings in distribution CI.

- Cross-platform strict clippy fixes:
  - loader: refactor runner callbacks (avoid silencing `clippy::too_many_arguments`).
  - oc-bridge: fix unix-only clippy issues and gate OS-specific error variants.

Pages:
- `.github/workflows/pages.yml` added with placeholder content under `pages/`.
- GitHub Pages enabled (build_type=workflow).
- Site: https://petitechose-midi-studio.github.io/distribution/

Channels:
- `channels/{stable,beta,nightly}.json` created.
- `schemas/channel-pointer.schema.json` created (includes `key_id`).

Channel pointer updates:
- Org policy blocks GitHub Actions from creating PRs.
- `main` requires PRs for changes.
- Therefore `publish.yml`/`nightly.yml` do not auto-update `channels/*.json` (they print URLs in job summary).
- Channel pointers can be updated manually via PR (use `scripts/update_channel_pointer.py`).
- Note: v1 install/rollback does not rely on channel pointers (stable uses `latest`; listing uses Releases API).

## Tests

Local (fast):
- Dry-run packaging script on fake inputs.

CI checks (required):
- Run publish workflow on a test tag (e.g. `v0.0.0-test.1`) and validate:
  - manifest signature verifies
  - sha256 matches
  - bundle contains expected files
  - channel pointer update instructions are emitted (and/or channel pointers updated manually)

Maintainer UX (next):
- Prefer publishing stable/beta via the maintainer command in Phase 02b (`ms release ...`).

## Security hardening (recommended)

High ROI measures to protect the signing key:

- Branch protection on `main`:
  - require PR
  - (recommended when there are 2+ maintainers) require Code Owner review + approvals
  - disallow force-push and deletion
  - require conversation resolution

- CODEOWNERS:
  - protect `.github/workflows/**`, `tools/**`, `schemas/**`, `channels/**`

- GitHub Actions environments:
  - `release` environment requires manual approval
  - store `MS_DIST_ED25519_SK` only as an environment secret on `release`
  - (optional) `nightly` environment for nightly-only secrets
