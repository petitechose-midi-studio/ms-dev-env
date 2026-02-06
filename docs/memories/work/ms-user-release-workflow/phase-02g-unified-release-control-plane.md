# Phase 02g: Unified Release Control Plane (Build Once + Promote)

Status: IN PROGRESS

## Goal

Migrate to a single release operating model across content and app:

- reliable: no hidden rebuild at publish time
- secure: signing keys only used behind protected environments
- reproducible: release provenance ties every published asset to exact CI candidates
- efficient: cancel superseded CI runs, avoid duplicate work
- low friction: maintainer UX remains `plan -> prepare -> publish` with strict auto defaults

## Validated choices (locked)

- Build model: **build once + promote**
- Candidate storage: **GitHub Releases RC** (draft releases)
- Stable/beta gate: **manual environment approval required**
- Release PR merge strategy: **non-squash** (rebase or merge)
- Migration strategy: **2 progressive phases** (no big bang)

## Full audit snapshot

Date: 2026-02-06

### Progress log

Completed in this phase so far:

- Added release PR non-squash behavior in `ms release` distribution merge path:
  - `ms/services/release/dist_repo.py` now uses `gh pr merge --rebase --auto`.
- Added workflow run cancellation (`concurrency.cancel-in-progress: true`) in:
  - `distribution`: `CI`, `Publish`, `Nightly`
  - `ms-manager`: `CI`, `Release`
  - `loader`: `CI`, `Release`
  - `open-control/bridge`: `CI`, `Release`
- Reduced duplicate loader CI work by scoping push CI to `main` only.
- Enabled/updated branch protection on:
  - `petitechose-midi-studio/ms-manager` `main`
  - `open-control/bridge` `main`
  with strict required checks + conversation resolution + no force push/deletion.
- Added first candidate-factory workflows (build once, durable draft RC release) in:
  - `midi-studio/loader`: `.github/workflows/candidate.yml`
  - `open-control/bridge`: `.github/workflows/candidate.yml`
  producing `rc-<sha>` draft releases with artifacts + `candidate.json` + `checksums.txt`.

### What is already strong

- `ms release` already provides strict CI-gated pin selection and safe planning:
  - `ms/cli/commands/release_cmd.py`
  - `ms/services/release/auto.py`
  - `ms/services/release/service.py`
- `distribution` publish pipeline has strong release controls:
  - explicit `environment: release` gate for stable/beta signing
  - manifest signing + verification + uploaded-assets verification
  - asset reuse logic for unchanged groups
  - workflows: `distribution/.github/workflows/publish.yml`, `distribution/.github/workflows/nightly.yml`
- `ms-dev-env` CI already uses cancellation via concurrency:
  - `.github/workflows/ci.yml`

### Current gaps (reliability/efficiency/security)

1) Duplicate build effort and inconsistent lifecycle

- `ms-manager` CI runs heavy Tauri build matrix (`--no-bundle`) and release workflow rebuilds again.
- `distribution` publish rebuilds loader/bridge/core/plugin-bitwig outputs from source checkouts at publish time.

2) Missing run cancellation in several repos

- No `concurrency.cancel-in-progress` in:
  - `ms-manager/.github/workflows/ci.yml`
  - `ms-manager/.github/workflows/release.yml`
  - `distribution/.github/workflows/publish.yml`
  - `distribution/.github/workflows/nightly.yml`
  - `midi-studio/loader/.github/workflows/*.yml`
  - `open-control/bridge/.github/workflows/*.yml`

3) Governance drift

- `ms-manager` main branch is currently not protected.
- `open-control/bridge` main branch is currently not protected.
- No repo rulesets are configured (including tag rulesets).

4) Provenance and run correlation gaps

- Dispatch run lookup in `ms/services/release/workflow.py` is best-effort and can race under concurrent dispatches.
- Published artifacts are not promoted from immutable candidate references; provenance is partly implicit.

5) Supply chain hardening gaps

- Third-party GitHub Actions are mostly pinned to tags, not commit SHAs.
- Branch protection does not require commit signatures.

## Target architecture

Use one control plane model for all releaseable products.

### Release lanes

1) Verify lane (fast CI)

- Trigger: PR + push
- Content: tests/lint/typecheck/smoke
- Must cancel superseded runs per ref
- No release secrets

2) Candidate lane (build once)

- Trigger: push on protected branches (`main`, optional `release/*`) + manual dispatch
- Builds release-grade artifacts once per SHA
- Produces immutable candidate metadata and checksums
- Publishes to **draft RC release** `rc-<sha>` in source repo
- No final channel publish

3) Promote lane (manual, controlled)

- Trigger: maintainer action (`ms release ... publish`)
- Inputs: selected SHAs + candidate references
- Downloads candidate artifacts only (no rebuild)
- Verifies checksums/provenance
- Signs channel manifests (content) and updater metadata (app)
- Publishes final release tags/assets

### Candidate storage contract (GitHub Releases RC)

Per source repo, per candidate SHA:

- Draft release tag: `rc-<sha>`
- Required assets:
  - product binaries/packages per platform
  - `candidate.json` (sha, workflow, run_id, toolchain, timestamps, artifact inventory)
  - `checksums.txt` (sha256 per file)
- Required properties:
  - idempotent upload/update for same SHA
  - immutable naming (no "latest" in candidate assets)

Notes:

- Draft release assets are durable and collaborator-visible, not publicly listed as published releases.
- Final end-user releases remain separate and durable until explicitly deleted.

## Migration plan (methodical and testable)

## Phase 1 (foundation): workflow reliability + candidate factory

Objective: produce immutable candidates and reduce CI waste, without changing end-user channel behavior yet.

### 1. Governance baseline hardening

Tasks:

- Protect `main` in `petitechose-midi-studio/ms-manager` with required checks.
- Protect `main` in `open-control/bridge` with required checks (if admin access available).
- Enforce PR merge for release-related changes (no direct push to protected branches).
- Update release PR merge policy to non-squash for release branches.
- Add environment for app publishing:
  - `ms-manager`: environment `app-release`, required reviewers, admin bypass disabled.

Tests:

- Direct push to protected `main` is blocked for non-exempt users.
- PR merge requires expected checks.
- Environment approval is required before app publish job can access secrets.

### 2. Concurrency and workflow hygiene everywhere

Tasks:

- Add `concurrency` with `cancel-in-progress: true` for verify and candidate workflows.
- Add tag-scoped concurrency for publish workflows.
- Keep least-privilege permissions (`contents: read` by default, write only where needed).

Tests:

- Push 3 quick commits on same branch; only latest run remains active.
- No accidental cancellation across different branches/tags.

### 3. Split verify vs candidate workflows in source repos

Repos:

- `midi-studio/loader`
- `open-control/bridge`
- `midi-studio/core`
- `midi-studio/plugin-bitwig`
- `ms-manager`

Tasks:

- Keep verify CI fast and branch-safe.
- Add `candidate.yml` per repo:
  - build release-grade outputs once per SHA
  - upload `candidate.json` + `checksums.txt`
  - publish draft RC release `rc-<sha>`
- For `ms-manager` candidate:
  - build installers/update bundles
  - do not publish final stable release in candidate lane

Tests:

- For one SHA in each repo, `rc-<sha>` exists with all required assets.
- `candidate.json` fields are complete and match run metadata.
- Re-running candidate for same SHA is idempotent.

### 4. Security hardening for workflow supply chain

Tasks:

- Pin third-party actions to immutable commit SHAs (not only tags).
- Add periodic dependency check for workflow action updates.

Tests:

- CI still passes after pinning.
- Workflow diff review clearly shows exact action SHAs.

### 5. Keep existing publish behavior as fallback (temporary)

Tasks:

- During Phase 1, do not remove current `distribution` rebuild path yet.
- Add feature flags to enable candidate download path later.

Tests:

- Existing stable/beta/nightly publish still works unchanged.

## Phase 2 (cutover): promotion-only publish + unified ms release

Objective: publish from validated candidates only, unify maintainer UX for content and app.

### 6. Distribution publish consumes candidates (no source rebuild)

Tasks:

- Extend release planning data to carry candidate provenance per repo SHA:
  - source repo
  - candidate tag (`rc-<sha>`)
  - workflow run id (optional but recommended)
  - expected asset checksums
- Update `distribution` publish/nightly workflows:
  - remove source repo compilation jobs for loader/bridge/core/plugin-bitwig in normal mode
  - fetch candidate assets from source RC releases
  - verify checksums/provenance before assembly/signing
  - keep emergency rebuild fallback behind explicit flag

Tests:

- Stable/beta release succeeds with candidate-only inputs.
- Inject checksum mismatch -> publish fails before signing.
- Candidate missing -> clear actionable failure message.

### 7. ms-manager publish becomes promotion-only

Tasks:

- Replace tag-build release flow with promotion flow:
  - input: version tag + candidate SHA
  - download candidate assets from `rc-<sha>`
  - sign updater payloads in `app-release` environment
  - generate `latest.json`
  - create final GitHub release
- Keep updater channel stable-only (current decision) unless explicitly changed later.

Tests:

- Install app version A, publish version B via promotion-only path, in-app badge/update works.
- `latest.json` includes linux/windows/darwin x64+arm64 entries.

### 8. Unified `ms release` orchestration (content + app)

Tasks:

- Add product-aware release config and planner in `ms/services/release/*`.
- Add commands (or sub-commands) with same lifecycle:
  - `plan` (auto/manual)
  - `prepare` (PR/version bump/spec changes)
  - `publish` (dispatch + watch)
- Keep strict auto defaults:
  - select latest green commits only
  - require candidate availability for selected SHAs
  - propose semantic bump but maintainer confirms
- Improve workflow dispatch correlation by adding nonce/correlation-id input and matching exact run.

Tests:

- `ms release ... --auto` picks only green SHAs with existing candidates.
- plan file replay remains deterministic.
- dispatch watches the exact triggered run (no race ambiguity).

### 9. Release PR merge behavior update

Tasks:

- Update release automation from squash to non-squash mode for release PRs.
- Ensure branch protection and required checks still enforce safety.

Tests:

- Release PR merge preserves expected commit ancestry.
- No regression in auto-merge behavior.

### 10. Decommission legacy rebuild paths

Tasks:

- After 2 successful end-to-end releases in candidate-only mode:
  - remove old source rebuild jobs from publish workflows
  - archive legacy release workflows in source repos if superseded

Tests:

- End-to-end release succeeds without any legacy path enabled.

## Test matrix (must pass before cutover)

1) CI cancellation

- Multiple pushes on same ref cancel older verify/candidate runs.

2) Candidate integrity

- Candidate metadata/checksums match uploaded assets.

3) Promotion integrity

- Publish fails closed on missing or mismatched candidate assets.

4) Security gates

- Stable/beta publish blocked until environment approval.

5) App updater correctness

- `latest.json` generated correctly and update installs from previous version.

6) Operational recovery

- Failed publish can be retried with same candidate without rebuild.

## Rollout and rollback strategy

Rollout:

- Run Phase 2 in shadow mode for 2 releases:
  - keep legacy rebuild path available
  - compare candidate-only outputs against legacy outputs

Rollback:

- If candidate path fails, rerun publish with explicit legacy fallback flag.
- Do not rotate signing keys during migration window.

## Success criteria

- Every final release is traceable to explicit candidate SHAs and candidate metadata.
- No duplicate heavy builds between verify and publish lanes.
- Superseded runs are canceled by default.
- Signing secrets are only reachable in protected publish environments.
- Maintainer UX is unified: same command model and safety checks for content and app.

## Risks and mitigations

- Risk: no admin rights on `open-control/bridge` branch protection.
  - Mitigation: enforce strict candidate + CI checks in `ms release`; treat unprotected repos as higher-risk and require explicit approval.

- Risk: candidate schema drift across repos.
  - Mitigation: define one `candidate.json` contract and add schema validation in publish lane.

- Risk: accidental publication of RC draft releases.
  - Mitigation: name + policy guardrails (`rc-*` tags only as draft), periodic audit workflow.
