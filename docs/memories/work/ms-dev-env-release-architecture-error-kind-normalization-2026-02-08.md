## Goal

Remove legacy/misleading `ReleaseError.kind` names (`dist_repo_*`) and replace them with neutral names that match actual usage across app + distribution + local repo ops.

This is a no-behavior-change refactor: only the error kind strings change, and the CLI mapping is updated accordingly.

## Motivation

- `dist_repo_failed/dist_repo_dirty` are used for failures across multiple repos (app, distribution, local I/O, some gh operations), so the name is misleading.
- Kind strings are part of internal contracts (tests + CLI exit-code mapping), so they must be updated atomically.

## New Kinds

- `repo_failed` (replaces `dist_repo_failed`)
- `repo_dirty` (replaces `dist_repo_dirty`)

## Definition of Done

- No references remain: `git grep -nE "dist_repo_(failed|dirty)" -- ms` returns 0.
- `uv run pytest` passes.
- `MS_ARCH_CHECKS=1 uv run pytest ms/test/architecture` passes.
- `uv run ruff check .` passes.
- `uv run pyright` passes.

## Progress Tracker

Legend: [ ] pending, [x] done, [~] in progress

- [x] 1. Update `ms/release/errors.py` Literal kind list
- [x] 2. Update all producers to emit `repo_failed/repo_dirty`
- [x] 3. Update CLI mapping (`release_error_code`) and kind checks
- [x] 4. Update tests asserting kinds
- [ ] 5. Validate + commit + push

## Notes

- This is a global string change; it must land atomically (code + tests + CLI exit mapping).
