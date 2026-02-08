## Goal

Remove redundant 1-line plan wrapper functions (`build_*_release_plan`) now that planners already return concrete plan dataclasses.

This reduces indirection and aligns with KISS.

## Scope

- Delete:
  - `ms/release/flow/app_plan.py::build_app_release_plan`
  - `ms/release/flow/content_plan.py::build_content_release_plan`
- Update callers:
  - `ms/cli/commands/release_app_commands.py`
  - `ms/cli/commands/release_content_commands.py`

## Definition of Done

- `uv run pytest` passes.
- `MS_ARCH_CHECKS=1 uv run pytest ms/test/architecture` passes.
- `uv run ruff check .` passes.
- `uv run pyright` passes.

## Progress Tracker

Legend: [ ] pending, [x] done

- [x] 1. Remove wrapper functions
- [x] 2. Update CLI callers
- [x] 3. Validate
- [ ] 4. Commit + PR
