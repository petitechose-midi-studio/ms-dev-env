# Phase 02h: Option 1 - Single Heavy Build per App Release

Status: TODO

## Why this phase exists

We validated the architecture direction: build once + promote.

But in practice, app releases still trigger too many heavy builds because `ms-manager` CI and Candidate are both heavy.

This phase defines the exact migration to keep the workflow safe, interactive, and simple while avoiding unnecessary recompute.

## Problem statement (simple)

Current app release behavior can run heavy builds at multiple points:

1) PR CI (`ms-manager/.github/workflows/ci.yml`) runs multi-OS Tauri build.
2) Merge to `main` triggers CI again (same heavy multi-OS build).
3) Merge to `main` also triggers Candidate heavy build.
4) Release promote is already no-rebuild (good), but it comes after the above.

Result: too many heavy builds for one release.

## Root cause

The verify lane and candidate lane are not clearly separated in `ms-manager`.

- Verify lane should be fast and cheap.
- Candidate lane should be the only heavy build lane.

## Target model (locked)

Option 1 (selected): Candidate is manual/dispatch-driven from release orchestration.

For app releases:

- Exactly one heavy build for the final release commit SHA.
- Final publish workflow promotes existing candidate assets only.
- No rebuild inside final release workflow.

## Target workflow (end-to-end, app)

Interactive operator flow:

1) `ms release app publish --channel <stable|beta> --auto --watch`
2) CLI selects latest CI-green commit (strict auto).
3) CLI proposes tag/version and asks confirmation.
4) CLI creates + merges version bump PR in `ms-manager`.
5) CLI resolves merged `main` HEAD SHA (`source_sha`).
6) CLI dispatches `ms-manager` Candidate for `source_sha`.
7) CLI waits Candidate success (`rc-<source_sha>` exists).
8) CLI dispatches `ms-manager` Release promote with `tag + source_sha`.
9) Maintainer/release-manager approves `app-release` environment.
10) Release publish completes from candidate assets (no rebuild).

## Current vs target (step-by-step)

Current (too expensive):

- PR CI heavy -> merge -> CI heavy again + Candidate heavy -> Release promote.

Target (single heavy build):

- PR CI light -> merge -> Candidate heavy (once, explicit SHA) -> Release promote.

## Exact implementation plan

### A) ms-manager verify lane becomes lightweight

File: `ms-manager/.github/workflows/ci.yml`

Changes:

- Keep `core (rust)` tests.
- Keep `frontend (svelte)` check/build.
- Remove heavy multi-OS `tauri build` matrix from CI.
- Optional safety: add one light tauri smoke check on ubuntu (`cargo check` / non-bundled minimal compile), but not cross-platform matrix.

Acceptance:

- PR CI duration drops significantly.
- No multi-OS heavy Tauri builds on PR/push CI.

### B) ms-manager candidate lane is the only heavy build lane

File: `ms-manager/.github/workflows/candidate.yml`

Changes:

- Trigger: `workflow_dispatch` only (remove push trigger on `main`).
- Inputs:
  - `source_sha` (required 40-char SHA)
- Checkout exact `source_sha`.
- Build heavy multi-platform Tauri artifacts.
- Publish draft candidate release `rc-<source_sha>`.

Acceptance:

- Candidate runs only when explicitly dispatched.
- Candidate assets are durable and deterministic for exact SHA.

### C) ms release app publish orchestrates candidate then promote

Files:

- `ms/cli/commands/release_cmd.py`
- `ms/services/release/workflow.py`
- `ms/services/release/service.py`

Changes:

- After PR merge, resolve exact merged `source_sha` from `ms-manager/main`.
- Dispatch candidate workflow with `source_sha` and wait completion.
- Dispatch release promote workflow with `tag + source_sha`.
- Keep interactive confirmations and `--watch` support.

Acceptance:

- One command drives candidate then promote.
- Operator experience remains simple and interactive.

### D) ms-manager release stays promote-only

File: `ms-manager/.github/workflows/release.yml`

Requirements:

- No build steps.
- Inputs include `tag` and `source_sha`.
- Validate candidate tag `rc-<source_sha>` exists.
- Download candidate assets.
- Rewrite `latest.json` URLs from candidate tag to final release tag.
- Publish final release assets.
- Keep environment gate `app-release`.

Acceptance:

- Release workflow contains no compile jobs.
- Final release can be retried without recompute.

### E) Branch protection check names update

Important operational step:

- If CI job names change (e.g., removing Tauri matrix), required status checks on `ms-manager/main` must be updated.

Policy target:

- Require only lightweight CI checks on PR merge gate.
- Candidate checks are not PR-gating checks; they are release-gating checks.

Acceptance:

- PR merges are not blocked by removed legacy check names.

## Security and safety guardrails

- Protected `main`, PR-only merges.
- Strict CI green requirement for selected SHAs.
- `app-release` environment approval required before publication.
- Candidate artifacts are immutable by SHA (`rc-<sha>` + checksums).
- Promote lane verifies provenance (tag + source_sha).

## Failure behavior (expected)

- Candidate fails:
  - publish halts before final release; no prod impact.
  - fix commit or infra, rerun from `ms release app publish`.
- Promote fails after candidate:
  - retry promote only; no recompute needed.
- Approval not granted:
  - workflow remains waiting; nothing is published.

## Interactive CLI examples (final UX)

Recommended one-shot:

- `ms release app publish --channel beta --auto --watch`

With explicit reproducible plan:

1) `ms release app plan --channel beta --auto --out .ms-release/app-beta.json`
2) `ms release app publish --plan .ms-release/app-beta.json --watch`

## Test plan (must pass)

1) No duplicate heavy builds

- Trigger one release publish.
- Verify exactly one heavy Candidate run for the final `source_sha`.
- Verify Release workflow does not compile.

2) Provenance

- Verify final release assets come from `rc-<source_sha>`.
- Verify `latest.json` points to final tag assets.

3) Safety

- Verify `app-release` approval is mandatory.
- Verify non-green auto selection blocks release.

4) Reproducibility

- Rerun promote for same tag/source after failure; no heavy rebuild required.

## Notes for content lane

The same model must be completed for content release:

- `distribution` publish should consume candidate artifacts for loader/bridge/core/plugin-bitwig.
- Remove source rebuild jobs once candidate consumption is proven stable.
