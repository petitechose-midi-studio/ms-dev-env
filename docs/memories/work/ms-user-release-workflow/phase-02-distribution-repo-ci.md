# Phase 02: Distribution Repo + CI (stable/beta/nightly) + Pages Demos

Status: IN PROGRESS

## Goal

Create the dedicated distribution repo and implement:

- Stable/beta publish workflow (manual / workflow_dispatch)
- Nightly workflow (scheduled, skip if not fully green)
- GitHub Pages demos (per channel)
- Channel pointer files (no GitHub API required for default install)

## Repo Layout (recommended)

- `channels/`
  - `stable.json`
  - `beta.json`
  - `nightly.json`
  - `stable-index.json` (optional, but recommended for Advanced UI)
  - `beta-index.json`
  - `nightly-index.json`

- `schemas/` (from Phase 01)

- `scripts/`
  - `select_latest_green.py` (nightly selection)
  - `package_assets.py` (deterministic names)
  - `publish_pages.py` (deploy demos)

- `.github/workflows/`
  - `publish.yml` (stable/beta)
  - `nightly.yml` (scheduled)
  - `pages.yml` (optional split)

## Workflows

### A) publish.yml (stable/beta)

Inputs:
- `channel`: stable|beta
- `tag`: vX.Y.Z or vX.Y.Z-beta.N
- `release_spec`: JSON (inline or artifact)

Steps (high-level):
1) Checkout distribution repo.
2) Checkout each pinned repo at exact SHA.
3) Build matrix (OS/arch):
   - `ms-manager` (Tauri)
   - `midi-studio-loader`
   - `oc-bridge` (+ config folder)
4) Build Ubuntu-only artifacts:
   - firmware hex bundles
   - Bitwig extension `.bwextension`
5) Package zips with deterministic names.
6) Generate + sign `manifest.json`.
7) Create GitHub Release + upload all assets.
8) Update `channels/<channel>.json` and optional index.
9) Deploy Pages demos for that channel.

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
- `midi-studio-bitwig-extension.zip` (OS-independent)
- `midi-studio-firmware-teensy.zip` (OS-independent)
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
- pages deploy works and URLs are recorded in manifest.
- channel pointers are updated atomically.

## Progress (recorded)

Repo created:
- `petitechose-midi-studio/distribution`

Baseline security applied:
- `SECURITY.md` documents key handling and hardening.
- `.github/CODEOWNERS` added for critical paths.
- `main` branch protection enabled (PR + Code Owner review + 1 approval; no force-push/deletion).
- GitHub Actions environments created:
  - `release` (required reviewer: `petitechose-audio`)
  - `nightly` (no reviewers)

Baseline CI:
- `.github/workflows/ci.yml` runs `cargo test` for the distribution repo.

## Tests

Local (fast):
- Dry-run packaging script on fake inputs.

CI checks (required):
- Run publish workflow on a test tag (e.g. `v0.0.0-test.1`) and validate:
  - manifest signature verifies
  - sha256 matches
  - bundle contains expected files
  - channels pointers updated

## Security hardening (recommended)

High ROI measures to protect the signing key:

- Branch protection on `main`:
  - require PR
  - require Code Owner review
  - require 1+ approvals
  - disallow force-push and deletion
  - require conversation resolution

- CODEOWNERS:
  - protect `.github/workflows/**`, `tools/**`, `schemas/**`, `channels/**`

- GitHub Actions environments:
  - `release` environment requires manual approval
  - store `MS_DIST_ED25519_SK` only as an environment secret on `release`
  - (optional) `nightly` environment for nightly-only secrets
