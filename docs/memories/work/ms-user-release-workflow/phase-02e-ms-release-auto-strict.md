# Phase 02e: `ms release --auto` (Strict, Low-Friction)

Status: DONE

## Goal

Make beta/stable releases as low-friction as possible while staying safe and reproducible.

Target UX:

- `ms release plan --auto --channel <beta|stable>`
- `ms release publish --auto --channel <beta|stable>`

"Auto" must be **strict by default**:

- Every pinned repo must be CI-gated (workflow configured).
- Product repos (core + plugin-bitwig): pin **remote HEAD** of the selected ref, and it must be **green**.
- Runtime repos (loader + oc-bridge): pin a **known-good** SHA by default (carry from previous release), and it must be **green**.
- Local workspaces must be clean and in sync with upstream for repos that are pinned to their remote HEAD.

## Current State (as of today)

- `ms release` supports interactive commit selection with CI markers for CI-gated repos.
- `ms release` supports a non-interactive mode via `--no-interactive` + `--repo id=sha` overrides.
- Plan files now preserve optional repo refs (so feature-branch releases remain traceable).
- `ms release publish` uses `--confirm-tag` for safe non-interactive confirmation.
- `ms release plan/prepare/publish` supports:
  - `--auto` (strict):
    - core/plugin-bitwig: pin remote HEAD (must be green)
    - loader/oc-bridge: carry previous release pins by default; propose bumps when newer green commits exist
  - `--ref id=branch`: override the ref used per repo (for feature branches)
  - interactive preflight warnings (dirty/ahead/behind/CI) with clickable GitHub URLs
- Distribution CI:
  - beta/stable: copy reuse + manual approval (environment `release`)
  - nightly: URL reuse + fully automated + skip publish when unchanged

Implemented:

- Canonical CI gating added for:
  - `petitechose-midi-studio/core` (`.github/workflows/ci.yml`)
  - `petitechose-midi-studio/plugin-bitwig` (`.github/workflows/ci.yml`)
- `ms release` config now treats `core` and `plugin-bitwig` as CI-gated.
- ms-dev-env CI is now tool-only + integration-smoke (no publishing); end-user publishing is distribution-only.

Missing for strict auto (still blocking real use):

- None at the mechanism level.
  - `--auto` will still block when the selected HEAD-pinned repos are not green (by design).

## Strict Auto Rules (LOCKED)

Given a repo entry (id, slug, ref, required_ci_workflow_file):

- If `required_ci_workflow_file` is missing: **auto is blocked**.

Pin selection:

- core/plugin-bitwig:
  - resolve `ref` to the **remote HEAD SHA**
  - require CI success on that exact SHA
- loader/oc-bridge:
  - default: carry pins from the previous release (same channel when possible)
  - require CI success on the carried SHA
  - if newer green commits exist on the default ref, `ms` should propose the bump (optional)

Feature branches:

- If a repo is explicitly targeted via `--ref id=feature/...`, treat it as HEAD-pinned:
  - pin remote HEAD of that branch
  - require CI green for that exact SHA

## Helpful Output (DX)

When auto is blocked, print actionable steps:

- Which repos are dirty (and list changed file paths)
- Which repos need push (ahead of upstream)
- Which repos are behind (need pull)
- Which repos are not CI-gated (and the workflow file + config field to add)

When auto succeeds, but optional bumps exist:

- Show proposed bumps for loader/oc-bridge (latest green commit on the ref).
- If the local repo is dirty/ahead/behind, surface that as a warning (because it usually means "push + wait CI").

## Next Actions


### A) CI ownership audit (done)

We must have exactly one canonical end-user release pipeline.

- Canonical end-user pipeline: `petitechose-midi-studio/distribution`
  - stable/beta/nightly publish + manifest signing + asset reuse
- Canonical "is this commit good?" signal: per-repo CI
  - each pinned repo must publish its own CI success result
  - `ms release --auto` consumes that signal

Action:

- Remove ms-dev-env workflows that publish end-user-like artifacts (avoid dual sources of truth).
- Keep ms-dev-env CI for the `ms` tool itself (typing/tests) and optional smoke builds that do NOT publish.

### B) Add canonical CI workflows to missing repos (done)

Implement minimal CI workflows in:

- `petitechose-midi-studio/core`
  - build PlatformIO `env:release` (firmware)
- `petitechose-midi-studio/plugin-bitwig`
  - build PlatformIO `env:release` (firmware)
  - optionally build `.bwextension` (if feasible/reliable in CI)

Then:

- Update `ms/services/release/config.py` to set `required_ci_workflow_file` for `core` and `plugin-bitwig`.
- Update `distribution/release-specs/nightly.template.json` to CI-gate `core` and `plugin-bitwig`.

### C) Validate strict auto end-to-end (done)

- On a feature branch per repo: push commits, wait for CI green.
- Run: `ms release plan --auto --channel beta --ref core=feature/... --ref plugin-bitwig=feature/...`.
- Expect: auto selects remote HEAD pins, then `ms release publish --auto ...` prepares + dispatches.

## Notes

- To reduce coupling on beta/stable, `--auto` pins:
  - `core` + `plugin-bitwig` to remote HEAD (must be green)
  - `loader` + `oc-bridge` by carrying the previous distribution release pins (must be green)
  - optional bumps are suggested when newer green commits exist for runtime repos
