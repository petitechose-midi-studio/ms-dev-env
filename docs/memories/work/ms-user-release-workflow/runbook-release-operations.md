# Runbook: Release Operations (Simple + Safe)

Status: ACTIVE

## Purpose

This runbook explains, in simple terms, how releases work today and what rules protect production.

It is written for contributors, maintainers, and release managers.

## Roles

- Contributor:
  - works on feature branches
  - opens PRs
  - cannot push directly to protected `main`
- Maintainer:
  - can merge PRs after CI is green
  - can run release commands
  - still cannot bypass branch protections on `main`
- Release manager:
  - approves protected release environments before publication/signing

## Non-negotiable safety rules

Across release repos, `main` is protected with:

- required status checks (`strict=true`)
- pull request required before merge
- conversation resolution required
- no force push, no branch deletion
- admins are also enforced (no bypass)

In `petitechose-midi-studio/*`, push rights to `main` are restricted to the `maintainers` team.

## Everyday workflow

### 1) Contributor flow

1. Create a branch.
2. Open a PR.
3. Wait for CI checks.
4. Maintainer merges if checks are green.

### 2) Maintainer flow

1. Review PR.
2. Ensure required checks are green.
3. Merge PR.

If a maintainer attempts direct push to protected `main`, GitHub blocks it.

## Content release flow (distribution)

Use `ms release` commands:

1. Plan:
   - `ms release content plan --channel <stable|beta> --auto`
2. Prepare PR in `distribution`:
   - `ms release content prepare --channel <stable|beta> --auto`
3. Publish:
   - `ms release content publish --channel <stable|beta> --auto --watch`

Compatibility aliases still work:

- `ms release plan|prepare|publish` (mapped to `content`)

What happens:

- `ms` selects CI-green SHAs (safe defaults).
- `ms` prepares/merges the distribution PR.
- `ms` dispatches `distribution` Publish workflow.
- Final publication is blocked on environment `release` approval.

No approval = no stable/beta publication.

## App release flow (ms-manager)

Current flow:

- `ms release app plan|prepare|publish` exists as command namespace but is currently a placeholder.
- Until app orchestration is fully implemented, use the manual steps below:

1. Version bump PR (package/Cargo/tauri versions).
2. Merge to `main`.
3. Create/push tag `vX.Y.Z`.
4. `Release` workflow runs.
5. Environment `app-release` approval is required before publishing.

No approval = no app publication.

## Candidate artifacts (build once)

For repos already migrated to candidate lane (`loader`, `open-control/bridge`):

- CI publishes draft release `rc-<sha>`
- assets include binaries + `candidate.json` + `checksums.txt`

This enables durable, reproducible promotion later.

## What if something fails?

- CI red on PR:
  - fix PR, push again
  - old run is canceled automatically (concurrency)
- publish workflow failed before environment approval:
  - fix input/config and re-dispatch
- publish workflow failed after approval:
  - investigate logs, then re-run publish with same tag/spec when safe

## Why unify app and content under one command model?

Yes, this is the recommended direction.

Target UX:

- `ms release content plan|prepare|publish ...`
- `ms release app plan|prepare|publish ...`

Benefits:

- one mental model for operators
- same safety contract (plan -> prepare -> publish)
- same CI-green + candidate checks
- same explicit approval gates

Backward compatibility recommendation:

- keep existing `ms release plan|prepare|publish` as aliases to `content` for a transition period.

## Practical policy summary (for anyone)

- Nobody merges untested code into `main`.
- Contributors always use PRs.
- Maintainers merge only when required checks are green.
- Stable/beta publication always requires protected environment approval.
- Release steps are explicit and repeatable.
