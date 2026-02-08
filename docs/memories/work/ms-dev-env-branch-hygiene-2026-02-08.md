## Goal

Keep the repository free of stale branches after large refactors.

## What Happened

- Release architecture work was developed as a stacked PR chain and later squash-merged to `main`.
- Squash merges do not preserve commit ancestry, so Git cannot reliably mark intermediate stack branches as "merged".
- The repository setting `delete_branch_on_merge` is disabled, so merged PR branches are not auto-deleted.

## Current Repository Settings (2026-02-08)

- default branch: `main`
- auto-merge: disabled
- auto-delete merged branches: disabled (`delete_branch_on_merge=false`)

## Cleanup Performed (2026-02-08)

Deleted obsolete remote branches (intermediate stack branches) after the refactor landed on `main`:

- `refactor/release-architecture-long-term`
- `refactor/release-architecture-a2-domain-extraction`
- `refactor/release-architecture-a3-infra-github`
- `refactor/release-architecture-a4-infra-repos`
- `refactor/release-architecture-a5-content-flow`
- `refactor/release-architecture-a6-app-flow`
- `refactor/release-architecture-a7-guided-split`
- `refactor/release-architecture-a8-shim-reduction`
- `refactor/release-architecture-a9-plan-artifacts-open-control`
- `refactor/release-architecture-a10-auto-ci-permissions`
- `refactor/release-architecture-b1-build-split`
- `refactor/release-architecture-b2-toolchains-split`
- `refactor/release-architecture-b3-repos-split`
- `refactor/release-architecture-b4-oc-cli-common-split`
- `refactor/release-architecture-b5-hardware-split`
- `refactor/release-architecture-b6-status-extraction`

After cleanup, only `origin/main` remains.

## Recommended Policy

1) Enable branch auto-delete on merge (`delete_branch_on_merge=true`).
2) Prefer small PRs and avoid long-lived stacks; if stacks are used, treat intermediate branches as disposable.
3) After any large squash merge, schedule a branch cleanup to remove obsolete heads.

## Commands

```bash
git fetch origin --prune
git branch -r

# delete a remote branch
git push origin --delete <branch>
```
