## Goal

Land the release-architecture refactor on `main` in a controlled, resumable way.

Current state (2026-02-08): work lives on a stacked PR chain (#35 -> #36 -> #37 -> #38 -> ... -> #50 -> #51). The head PR is #51.

## Options

### Option A (Recommended): Collapse stack by retargeting PR #51 to `main`

Pros:

- Single merge to main.
- Avoids babysitting old PRs with failing/obsolete checks.
- Keeps the current head branch (which already passes CI) as the source of truth.

Cons:

- Big PR diff (already large), less incremental.

Steps:

1) Change base of PR #51 to `main`.
2) Re-run CI (should be automatic) and ensure `mergeable` stays green.
3) Get at least 1 approval.
4) Merge (prefer squash) and delete branch.
5) Close redundant stacked PRs (#35/#36/#37/#38/#50) or mark as superseded.

### Option B: Merge the stack bottom-up

Pros:

- Preserves incremental review.

Cons:

- Requires every PR to be mergeable and pass required checks.
- Several early PRs show an `architecture (advisory)` failing check today.

Steps:

1) Fix/neutralize the failing `architecture (advisory)` checks on PRs #35/#36/#37/#38.
2) Merge #35 into main, retarget #36 to main, merge, etc.
3) Continue through #50 then #51.

## Safety Checks

- Ensure the head branch is not behind `main`.
- Ensure `gh pr checks 51` all green.
- Ensure the PR is mergeable.
- Ensure tests pass locally: `uv run pytest`.

## Progress Tracker

Legend: [ ] pending, [x] done, [~] in progress

- [x] Verify PR #51 checks green and mergeable
- [x] Pick merge option (A recommended)
- [~] Execute selected option
- [ ] Post-merge cleanup (close/supersede redundant PRs)

## Commands

```bash
gh pr view 51
gh pr checks 51

# Option A (retarget base)
gh pr edit 51 --base main

# Merge (after approval)
gh pr merge 51 --squash --delete-branch
```

## Execution Notes

- 2026-02-08: PR #51 base was changed to `main` (`gh pr edit 51 --base main`).
- After base retargeting, the PR diff now includes the full stacked work (expected: large diff). Keep further changes minimal until merge.
