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

Use `ms release` commands:

1. Plan:
   - `ms release app plan --channel <stable|beta> --auto`
2. Prepare PR in `ms-manager`:
   - `ms release app prepare --channel <stable|beta> --auto`
3. Publish:
   - `ms release app publish --channel <stable|beta> --auto --watch`

What happens:

- `ms` selects CI-green SHAs (safe defaults).
- `ms` prepares/merges the version bump PR in `ms-manager`.
- `ms` dispatches `ms-manager` Candidate for the exact merged `source_sha`; candidate stores draft `rc-<sha>` assets.
- `ms` dispatches `ms-manager` Release workflow, which promotes candidate assets to final tag release (no rebuild).
- Final publication is blocked on environment `app-release` approval.

App package policy:

- Windows: MSI
- macOS: DMG
- Linux: DEB/RPM
- App updates are manual for all platforms (UI redirects to GitHub `releases/latest`).

No approval = no app publication.

Transition note:

- The release lane is already promote-only (no rebuild in final publish).
- Verify lane optimization to remove duplicate heavy builds is tracked in:
  - `docs/memories/work/ms-user-release-workflow/phase-02h-option1-single-heavy-build.md`

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
