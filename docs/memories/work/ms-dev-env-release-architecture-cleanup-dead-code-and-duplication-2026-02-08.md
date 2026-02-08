## Goal

Make the post-C1 release refactor genuinely "clean": no dead code, no duplicated parsing logic, and a clear next trajectory for removing the remaining structural debt.

This is a continuation after commit `2771d72` (legacy `ms/services/release/*` retired).

## Scope (This Action Plan)

- Delete confirmed dead code (unused functions/modules).
- Remove duplicated override parsing/validation (`--repo`, `--ref`, `--auto`) by extracting a single canonical implementation.
- Keep behavior stable (no user-facing changes).
- Keep architecture/layering constraints green.

## Definition of Done

- `uv run pytest` passes.
- `MS_ARCH_CHECKS=1 uv run pytest ms/test/architecture` passes.
- `uv run ruff check .` passes.
- `uv run pyright` passes.

## Progress Tracker

Legend: [ ] pending, [x] done, [~] in progress

- [x] 0. Baseline check after `2771d72`
- [x] 1. Remove dead CLI helpers in `ms/cli/commands/release_common.py`
- [x] 2. Remove unused `ms/release/contracts.py` (or make it used)
- [x] 3. Extract canonical overrides parsing to `ms/release/resolve/overrides.py`
- [x] 4. Update `ms/release/resolve/*_inputs.py` to use the shared module
- [x] 5. Update CLI import(s) for override parsing
- [x] 6. Validate (pytest + arch + ruff + pyright)
- [x] 7. Record follow-up trajectory (next waves)

## Trajectory (Next Waves After This Plan)

These are intentionally NOT part of this plan (bigger surface / potential behavior change), but they are the next steps to reach "no legacy":

1) Replace "stringly typed" status returns like `"(already merged) ..."` with structured results for prepare steps (app + content).
2) Reduce duplication/boilerplate in `ms/release/view/*` by introducing view DTOs instead of large `Protocol` shape mirrors.
3) Remove remaining compatibility surface in release CLI (top-level `ms release plan|prepare|publish|remove`) once downstream users are migrated.
4) Tighten architecture tests (update legacy hotspot list + budgets to reflect current reality).

## What Changed (Executed)

- Removed dead code:
  - deleted `ms/release/contracts.py` (unused)
  - removed unused helpers from `ms/cli/commands/release_common.py`
- Deduplicated override parsing:
  - added `ms/release/resolve/overrides.py`
  - updated `ms/release/resolve/app_inputs.py`
  - updated `ms/release/resolve/content_inputs.py`
  - updated `ms/cli/commands/release_content_commands.py`
- Updated guardrails/docs to avoid stale legacy references:
  - `ms/test/architecture/test_module_size_limits.py` (removed deleted `services/release/*` hotspots)
  - `docs/memories/work/ms-dev-env-release-architecture-long-term-plan-2026-02-07.md` (treeview + notes)

## Verification

```bash
uv run pytest
MS_ARCH_CHECKS=1 uv run pytest ms/test/architecture
uv run ruff check .
uv run pyright
```

Results: all green.
