# Next steps (2026-01-28)

This document is the "executable plan" from the current state.
Every step is designed to be small, testable, and traceable.

## Current state (baseline)

- CLI Phase 6 is done (verb-based `ms` surface).
- CI smoke is green.
- Full Builds is green (baseline run):
  - https://github.com/petitechose-audio/workspace/actions/runs/21435915307

## Step 1: Finalize Phase 7 (CI matrix)

**Goal**: adjust CI to match product intent:

- native builds on all platforms
- WASM builds only once (Ubuntu)

### 1.1 Update Full Builds matrix

Change `.github/workflows/builds.yml`:

- Windows:
  - enable `ms build core --target native`
  - disable WASM
- Ubuntu:
  - native + WASM
- macOS:
  - native only
- Fedora:
  - native only (keep distro coverage)

Add WASM builds for both apps on Ubuntu:

- `ms build core --target wasm`
- `ms build bitwig --target wasm`

### 1.2 Verification

- Trigger a Full Builds run:

```bash
gh workflow run builds.yml --ref main
gh run list -L 3 --workflow "Full Builds"
```

- Confirm job success:

```bash
gh run view <run-id> --json status,conclusion,url
gh run view <run-id> --log-failed
```

### 1.3 Close Phase 7

When the new matrix is green:

- Mark `docs/memories/work/refactor-all-dev-cli-dx-max/phase-7-ci-matrix.md` as `completed`
- Update `docs/memories/work/refactor-all-dev-cli-dx-max/STATUS.md` to `Phase 7 (ci matrix): completed`
- Record the run URL in the Phase 7 work log.

## Step 2: Implement Phase 8 (Web demos)

**Goal**: publish static demo pages for core + bitwig.

### 2.1 Decide how the demo connects

The WASM apps connect to local `oc-bridge` via WebSocket:

- core: `ws://localhost:8100`
- bitwig: `ws://localhost:8101`

We must validate browser behavior when the page is served from HTTPS (GitHub Pages) but
connects to `ws://localhost`.

If browsers block it (mixed content), fallback is:

- host the same static files locally via `ms web <app>` (HTTP localhost is treated as a secure origin)

### 2.2 Add a Pages workflow

Add a GitHub Actions workflow:

- builds WASM on Ubuntu only
- copies artifacts into a Pages site layout:
  - `demo/core/latest/`
  - `demo/bitwig/latest/`
- deploys via `actions/deploy-pages`

### 2.3 Add static wrapper pages (tracked)

Add tracked HTML pages that:

- explain prerequisites (run bridge locally, WebMIDI permission, Bitwig extension mode)
- link to the built Emscripten html (`midi_studio_core.html` / `midi_studio_bitwig.html`)

### 2.4 Verification

- Run the Pages workflow and confirm the deployed URLs respond.
- Manual validation (real browser):
  - open `/demo/core/latest/` and `/demo/bitwig/latest/`
  - verify UI loads
  - verify behavior with local bridge running

### 2.5 Update Phase 8 docs

- Set `docs/memories/work/refactor-all-dev-cli-dx-max/phase-8-web-demos.md` to `started` when implementation begins.
- Set to `completed` once Pages deploy is verified.

## Step 3: Repo migration to `midi-studio/ms-dev-env`

**Goal**: governance + naming + visibility coherence.

Steps are documented in:

- `docs/memories/work/refactor-all-dev-cli-dx-max/repo-migration.md`

### Verification

- repo exists under org + correct name + public
- local `origin` updated
- Pages URL updated (base changes)

## Step 4: Post-migration follow-ups

- Update any hardcoded URLs in docs to the new repo.
- If old Pages links were shared, publish a redirect on the old Pages site.
