# Phase 02g/02h Execution Plan: Manual App Updates + Native Packages

Status: ACTIVE PLAN

Date: 2026-02-07

## Scope

This plan covers only the short-term delivery for:

- Phase 02g: Unified release control plane (build once + promote)
- Phase 02h: Single heavy build per app release

And locks the packaging/update policy for the app itself (`ms-manager`):

- App updates are manual on all platforms (open GitHub latest release page).
- In-app automatic update/install is removed for the app binary.
- In-app updates remain for content/runtime bundles only (distribution manifest flow).

## Locked decisions (no ambiguity)

1) App update policy

- `ms-manager` app binary is updated manually by the user.
- The app may show an "update available" badge, but install action is:
  - open `https://github.com/petitechose-midi-studio/ms-manager/releases/latest`
- No Tauri updater install flow (`download_and_install`) in v1.

2) Package formats to publish

- Linux: `.deb` and `.rpm`.
- Windows: `.msi` (WiX).
- macOS: `.dmg`.
- AppImage is removed from release outputs.

3) 02h build model (app lane)

- Verify lane (CI) stays lightweight.
- Candidate lane is the only heavy multi-OS packaging lane.
- Release lane is promote-only (no rebuild).

## Why this direction

- Keeps behavior consistent across Windows/macOS/Linux.
- Removes updater-specific complexity (`latest.json` rewriting, updater key management for app binary install).
- Reduces Linux runtime variance seen with AppImage (blank/gray UI cases) by relying on native distro packages.
- Preserves strict separation:
  - app distribution = manual packages/releases
  - content distribution = signed manifest, in-app managed

## Deliverables

At the end of this plan, we must have:

- `ms-manager` candidate workflow producing only: `msi`, `dmg`, `deb`, `rpm` artifacts (+ checksums/metadata).
- `ms-manager` release workflow promoting candidate assets without any build step.
- `ms release app publish` orchestrating:
  - candidate dispatch for exact merged `source_sha`
  - candidate watch/success gate
  - release dispatch with `tag + source_sha`
- `ms-manager` UI action for app update changed to "open latest release page".
- No in-app app-binary auto-install code path remaining.

## Implementation plan (ordered, explicit)

### Step 0 - Docs and contract alignment

Repo: `ms-dev-env`

Files to update:

- `docs/memories/work/ms-user-release-workflow/phase-02h-option1-single-heavy-build.md`
- `docs/memories/work/ms-user-release-workflow/phase-07a-ms-manager-app-updates.md`
- `docs/memories/work/ms-user-release-workflow/phase-07-bootstrap-installer.md`
- `docs/memories/work/ms-user-release-workflow/runbook-release-operations.md`

Required edits:

- Replace AppImage references with `.deb/.rpm` for Linux app packaging.
- Replace NSIS-only wording with MSI (WiX) for Windows app packaging.
- Replace "Tauri updater installs app" with "manual app update via GitHub latest page".
- Keep explicit note that runtime/content updates remain in-app via distribution manifests.

Exit check:

- No contradictory statement remains in docs for app packaging/update policy.

### Step 1 - Make app verify lane lightweight (02h)

Repo: `petitechose-midi-studio/ms-manager`

File:

- `.github/workflows/ci.yml`

Required edits:

- Keep:
  - `core (rust)` tests
  - frontend checks/build
- Remove heavy multi-OS Tauri packaging/build matrix from CI.
- Optional: add one lightweight Tauri compile smoke check on Ubuntu only (`cargo check`), no bundle.

Exit check:

- CI runtime drops and no multi-OS packaging is triggered on PR/push.

### Step 2 - Candidate is the only heavy lane (02h)

Repo: `petitechose-midi-studio/ms-manager`

File:

- `.github/workflows/candidate.yml`

Required edits:

- Trigger policy:
  - keep `workflow_dispatch`
  - remove `push` trigger from `main`
- Inputs:
  - `source_sha` required (40-char commit SHA)
- Checkout exact `source_sha`.
- Build heavy multi-OS packages once.
- Publish draft release `rc-<source_sha>`.
- Produce candidate metadata assets:
  - `candidate.json` (sha, workflow, run id, timestamps, artifact list)
  - `checksums.txt`
- Package target validation:
  - Windows MSI only (no NSIS setup exe)
  - macOS DMG
  - Linux DEB/RPM
  - no AppImage

Exit check:

- Running candidate twice on same `source_sha` is idempotent.
- Candidate release contains only expected package types and metadata.

### Step 3 - Promote-only release workflow (02g/02h)

Repo: `petitechose-midi-studio/ms-manager`

File:

- `.github/workflows/release.yml`

Required edits:

- Keep `workflow_dispatch` path with inputs `tag`, `source_sha`, `request_id`.
- Remove any build/compile step.
- Validate `source_sha` format and resolve candidate tag `rc-<source_sha>`.
- Download candidate assets.
- Publish final release by promoting those exact assets.
- Keep environment approval gate `app-release`.
- Remove updater-specific release logic:
  - no `latest.json` URL rewrite
  - no dependency on updater-generated install metadata

Exit check:

- Release workflow succeeds without compilation.
- Re-run promote for same `tag/source_sha` works without recompute.

### Step 4 - Remove app-binary auto-updater behavior

Repo: `petitechose-midi-studio/ms-manager`

Files (expected):

- `src-tauri/tauri.conf.json`
- `src-tauri/src/lib.rs`
- `src-tauri/src/commands/app_update.rs`
- `src/lib/state/dashboard.ts`
- `src/lib/screens/Dashboard.svelte`
- `src/lib/api/client.ts`
- `src/lib/api/types.ts`

Required edits:

- Remove app install flow via Tauri updater (`download_and_install` path).
- Replace install action with opener to GitHub latest release page.
- Keep optional check badge behavior (if version check remains), but action is always manual redirect.
- Remove now-unused updater wiring/config if no longer required.

Exit check:

- "Update ms-manager" no longer installs in-app.
- Clicking update opens browser to releases/latest.

### Step 5 - Package target cutover in Tauri config

Repo: `petitechose-midi-studio/ms-manager`

File:

- `src-tauri/tauri.conf.json`

Required edits:

- Bundle targets must be exactly:
  - `msi`
  - `dmg`
  - `deb`
  - `rpm`
- Remove:
  - `appimage`
  - `nsis`
- Configure Windows WebView2 strategy compatible with MSI/WiX (`downloadBootstrapper`).
- Keep macOS bundle target as DMG (optionally keep `app` as non-primary internal artifact only if needed).

Exit check:

- Candidate and release artifacts match the locked package policy.

### Step 6 - `ms release app publish` must orchestrate candidate then promote

Repo: `ms-dev-env`

Files:

- `ms/services/release/config.py`
- `ms/services/release/workflow.py`
- `ms/services/release/service.py`
- `ms/cli/commands/release_cmd.py`

Required edits:

- Add app candidate workflow constant (e.g. `candidate.yml`).
- Add workflow dispatch function for app candidate with `source_sha` input.
- In `ms release app publish` flow:
  1. prepare + merge version PR
  2. resolve merged `source_sha`
  3. dispatch candidate for that exact `source_sha`
  4. wait candidate success (especially when `--watch`)
  5. dispatch release promote with `tag + source_sha`
- Keep dispatch correlation via `request_id`.

Exit check:

- One command performs candidate then promote for exact SHA provenance.
- No hidden candidate run dependency on push triggers.

### Step 7 - Branch protection/required checks sync

Repos:

- `petitechose-midi-studio/ms-manager`

Required operations:

- Update required status checks to reflect new CI job names after CI simplification.
- Ensure removed checks are no longer required.

Exit check:

- PR merge gate blocks only on intended lightweight checks.
- Release gating remains in candidate + app-release environment approvals.

## Test plan (must pass)

### A) Pipeline behavior

1. Trigger one app release from CLI.
2. Verify exactly one heavy candidate run for final `source_sha`.
3. Verify release workflow performs promotion only (no compile logs/jobs).

### B) Artifact contract

For candidate and final release:

- present: Windows MSI, macOS DMG, Linux DEB/RPM
- absent: AppImage, NSIS setup exe
- present: checksums + candidate metadata (candidate release)

### C) App update UX (manual)

1. Install app version A.
2. Publish app version B.
3. Launch A:
   - update badge appears (if check enabled)
   - update action opens GitHub `releases/latest`
   - no in-app auto-install is attempted

### D) Content update regression guard

1. From app UI, run normal runtime/content update flow.
2. Verify signed distribution manifest flow still works unchanged.

## Rollback plan

If candidate/promote cutover fails:

- Temporarily re-enable `push` trigger on candidate while fixing orchestration.
- Keep release promote-only (do not reintroduce rebuild in release lane).
- Do not reintroduce app auto-updater install path as emergency fallback.

## Definition of done

This plan is complete only when all items are true:

- 02h app-lane objective met: one heavy build per release SHA.
- 02g app promote lane remains no-rebuild and approval-gated.
- App packaging policy in production matches locked formats (MSI/DMG/DEB/RPM).
- App update policy is manual and consistent on all 3 platforms.
- Documentation and runbook reflect the new policy without contradictions.
