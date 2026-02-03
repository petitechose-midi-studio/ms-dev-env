# Phase 02e: `ms release --auto` (Strict, Low-Friction)

Status: IN PROGRESS

## Goal

Make beta/stable releases as low-friction as possible while staying safe and reproducible.

Target UX:

- `ms release plan --auto --channel <beta|stable>`
- `ms release publish --auto --channel <beta|stable>`

"Auto" must be **strict by default**:

- Every pinned repo must be CI-gated (workflow configured).
- The selected SHA must be **the remote HEAD** of the selected branch (ref) and must be **green**.
- Local workspaces must be clean and in sync with upstream (no dirty/ahead/behind) to avoid accidentally releasing something other than what the maintainer sees locally.

## Current State (as of today)

- `ms release` supports interactive commit selection with CI markers for CI-gated repos.
- `ms release` supports a non-interactive mode via `--no-interactive` + `--repo id=sha` overrides.
- `ms release publish` uses `--confirm-tag` for safe non-interactive confirmation.
- Distribution CI:
  - beta/stable: copy reuse + manual approval (environment `release`)
  - nightly: URL reuse + fully automated + skip publish when unchanged

Missing for strict auto:

- A release readiness preflight that:
  - detects dirty repos and lists changed files
  - detects repos that are ahead/behind and need push/pull
  - checks that the remote HEAD commit is green for each CI-gated repo
- CI gating for all pinned repos (at least core + plugin-bitwig).

## Strict Auto Rules (LOCKED)

Given a repo entry (id, slug, ref, required_ci_workflow_file):

- Resolve `ref` to the remote head SHA.
- If `required_ci_workflow_file` is missing: **auto is blocked**.
- If the head SHA has no successful CI run for the required workflow on that branch:
  - **auto is blocked**
  - the CLI must explain how to proceed: push changes, wait for CI green, rerun

## Helpful Output (DX)

When auto is blocked, print actionable steps:

- Which repos are dirty (and list changed file paths)
- Which repos need push (ahead of upstream)
- Which repos are behind (need pull)
- Which repos are not CI-gated (and the workflow file + config field to add)

## Next Actions

- Implement `--auto` selection for `ms release plan/prepare/publish`.
- Add a shared preflight routine used by interactive and auto modes.
- Add CI gating for core + plugin-bitwig, then mark auto mode as fully supported.
