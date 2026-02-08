## Goal

Remove the legacy release facade under `ms/services/release/*` by moving the remaining canonical use-cases into the release bounded context (`ms/release/*`), then updating all call sites (CLI + guided flows + tests) to import from `ms/release` only.

This is intentionally written as a runbook so any developer can resume mid-flight.

## Scope

- Move these public APIs out of `ms/services/release/service.py`:
  - `plan_release`
  - `prepare_distribution_pr`
  - `publish_distribution_release`
  - `plan_app_release`
  - `prepare_app_pr` (+ `AppPrepareResult`)
  - `publish_app_release`
- Move these public APIs out of `ms/services/release/remove.py`:
  - `validate_remove_tags`
  - `remove_distribution_artifacts` (+ `RemovePlan`)
  - `delete_github_releases`
- Update all imports in:
  - `ms/cli/commands/release_content_commands.py`
  - `ms/cli/commands/release_app_commands.py`
  - `ms/cli/release_guided_content.py`
  - `ms/cli/release_guided_app.py`
  - `ms/test/cli/test_release_guided_flows.py`
- Delete `ms/services/release/`.
- Add an architecture guard preventing `ms/cli` from importing `ms/services/release`.

## Non-goals

- No behavior changes (keep outputs, error kinds, idempotency behavior).
- No large API redesign (e.g. changing `plan_app_release` return type).
- No refactor of `ReleaseError.kind` taxonomy in this pass.

## Definition of Done

- `git grep -nE "^(from|import) ms\\.services\\.release" -- ms` returns 0 results.
- `ms/services/release/` directory is removed.
- `uv run pytest` passes.
- `MS_ARCH_CHECKS=1 uv run pytest ms/test/architecture` passes.
- `uv run ruff check .` passes.
- `uv run pyright` passes.

## Progress Tracker

Legend: [ ] pending, [x] done, [~] in progress

- [x] 0. Baseline: verify clean tree + current tests
- [x] 1. Move content planning: `plan_release` -> `ms/release/flow/content_plan.py`
- [x] 2. Move app planning: `plan_app_release` -> `ms/release/flow/app_plan.py`
- [x] 3. Move content prepare: `prepare_distribution_pr` -> `ms/release/flow/content_prepare.py`
- [x] 4. Move content publish: `publish_distribution_release` -> `ms/release/flow/content_publish.py`
- [x] 5. Move app prepare: `AppPrepareResult` + `prepare_app_pr` -> `ms/release/flow/app_prepare.py`
- [x] 6. Move app publish: `publish_app_release` -> `ms/release/flow/app_publish.py`
- [x] 7. Move remove ops: `RemovePlan` + delete helpers -> `ms/release/flow/content_remove.py`
- [x] 8. Update imports: CLI + guided + tests
- [x] 9. Delete `ms/services/release/`
- [x] 10. Add arch guard: forbid `ms.cli` -> `ms.services.release`
- [x] 11. Validate (pytest + arch + ruff + pyright)
- [x] 12. Final sweep + document final state

## Step 0 - Baseline

Commands:

```bash
git status --porcelain=v1
git branch --show-current
uv run pytest
MS_ARCH_CHECKS=1 uv run pytest ms/test/architecture
uv run ruff check .
uv run pyright
```

Notes:

- Branch: `refactor/release-architecture-c1-shim-removal`
- Working tree: clean
- Tests: OK (see CLI output)

## Final State (What Changed)

Moved implementations into the release bounded context:

- Planning:
  - `ms/release/flow/content_plan.py::plan_release`
  - `ms/release/flow/app_plan.py::plan_app_release`
- Prepare:
  - `ms/release/flow/content_prepare.py::prepare_distribution_pr`
  - `ms/release/flow/app_prepare.py::prepare_app_pr`
  - `ms/release/flow/app_prepare.py::AppPrepareResult`
- Publish:
  - `ms/release/flow/content_publish.py::publish_distribution_release`
  - `ms/release/flow/app_publish.py::publish_app_release`
- Remove:
  - `ms/release/flow/content_remove.py::{validate_remove_tags, remove_distribution_artifacts, delete_github_releases, RemovePlan}`

Deleted legacy modules:

- `ms/services/release/service.py`
- `ms/services/release/remove.py`
- `ms/services/release/__init__.py`

Updated call sites:

- `ms/cli/commands/release_content_commands.py`
- `ms/cli/commands/release_app_commands.py`
- `ms/cli/release_guided_content.py`
- `ms/cli/release_guided_app.py`
- `ms/test/cli/test_release_guided_flows.py`

Added an architecture guard:

- `ms/test/architecture/test_import_layers.py` now enforces `ms/cli` must not import `ms.services.release`.

## Final Verification

```bash
git grep -nE "^(from|import) ms\\.services\\.release" -- ms
uv run pytest
MS_ARCH_CHECKS=1 uv run pytest ms/test/architecture
uv run ruff check .
uv run pyright
```

## Follow-ups

- Dead code + duplication cleanup: `docs/memories/work/ms-dev-env-release-architecture-cleanup-dead-code-and-duplication-2026-02-08.md`
- Typed PR outcomes (remove fake `pr_url` strings): `docs/memories/work/ms-dev-env-release-architecture-typed-pr-outcomes-2026-02-08.md`

## Execution Plan (Methodical Order)

This runbook proceeds in a low-risk order:

1) Copy/move implementations into `ms/release/flow/*` while keeping signatures.
2) Update imports to point at the new locations.
3) Delete legacy modules.
4) Lock the boundary with an architecture test.
5) Run validations and do a final grep sweep.

## Mapping: Old -> New

- `ms/services/release/service.py::plan_release` -> `ms/release/flow/content_plan.py::plan_release`
- `ms/services/release/service.py::prepare_distribution_pr` -> `ms/release/flow/content_prepare.py::prepare_distribution_pr`
- `ms/services/release/service.py::publish_distribution_release` -> `ms/release/flow/content_publish.py::publish_distribution_release`
- `ms/services/release/service.py::plan_app_release` -> `ms/release/flow/app_plan.py::plan_app_release`
- `ms/services/release/service.py::AppPrepareResult` -> `ms/release/flow/app_prepare.py::AppPrepareResult`
- `ms/services/release/service.py::prepare_app_pr` -> `ms/release/flow/app_prepare.py::prepare_app_pr`
- `ms/services/release/service.py::publish_app_release` -> `ms/release/flow/app_publish.py::publish_app_release`

- `ms/services/release/remove.py::RemovePlan` -> `ms/release/flow/content_remove.py::RemovePlan`
- `ms/services/release/remove.py::validate_remove_tags` -> `ms/release/flow/content_remove.py::validate_remove_tags`
- `ms/services/release/remove.py::remove_distribution_artifacts` -> `ms/release/flow/content_remove.py::remove_distribution_artifacts`
- `ms/services/release/remove.py::delete_github_releases` -> `ms/release/flow/content_remove.py::delete_github_releases`

## Validation Strategy (While Refactoring)

- After each moved module: run targeted tests if available, else `uv run pytest ms/test/cli/test_release_guided_flows.py -q`.
- Before deleting legacy modules: run `rg "ms\\.services\\.release" -n ms` and ensure only the legacy files remain.
- After deleting legacy modules: run full validations (DoD).

## Rollback Strategy

- If something breaks unexpectedly, revert by restoring `ms/services/release/*` and re-pointing imports.
- Avoid partial deletes: only delete `ms/services/release/` after all imports are updated and tests pass.
