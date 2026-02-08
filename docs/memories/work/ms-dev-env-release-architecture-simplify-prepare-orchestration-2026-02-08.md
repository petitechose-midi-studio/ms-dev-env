## Goal

Simplify prepare orchestration by removing dependency-injection style `*_fn` parameters where they are only used by the CLI.

Keep the orchestration in `ms/release/flow/*` (not the CLI), but make it concrete: call `ensure_ci_green` and `prepare_*_pr` directly.

## Scope

- `ms/release/flow/content_prepare.py::prepare_content_release_distribution`
- `ms/release/flow/app_prepare.py::prepare_app_release_distribution`
- Update callers:
  - `ms/cli/commands/release_content_commands.py`
  - `ms/cli/commands/release_app_commands.py`

## Definition of Done

- `uv run pytest` passes.
- `MS_ARCH_CHECKS=1 uv run pytest ms/test/architecture` passes.
- `uv run ruff check .` passes.
- `uv run pyright` passes.

## Progress Tracker

Legend: [ ] pending, [x] done

- [x] 1. Make prepare orchestrators concrete (remove `*_fn` params)
- [x] 2. Update CLI callers
- [x] 3. Validate
- [ ] 4. Commit + PR
