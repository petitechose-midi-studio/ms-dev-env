# Phase 3: Repos sync (git-only)

**Scope**: repos sync
**Status**: planned
**Created**: 2026-01-27
**Updated**: 2026-01-27

## Goal

- Repo sync works with `git` only (no `gh`, no GH auth).
- Sync is deterministic via a pinned manifest.
- Safety policy preserved:
  - never touches dirty repos
  - no destructive operations

## Planned commits (atomic)

1. `feat(repos): add pinned repo manifest`
   - Add `ms/data/repos.toml` listing required repos + URLs + checkout paths.

2. `refactor(repos): sync from manifest (drop gh)`
   - Rewrite `ms/services/repos.py`.
   - Update CLI hints to `ms sync --repos`.
   - Keep `pull --ff-only`.

3. `test(repos): add local repo sync tests`
   - Use temporary local git repos to test clone/pull/skip dirty.

## Work log

- 2026-01-27: Phase created (no code changes yet).

## Decisions

- (pending)

## Plan deviations

- (none)

## Verification (minimum)

```bash
uv run pytest ms/test -q
uv run ms sync --repos --dry-run
```

Manual validation checklist:

- Dirty repo is skipped and reported.
- Repo on non-default branch is skipped and reported.

## Sources

- `ms/services/repos.py`
- `ms/cli/commands/sync.py`
