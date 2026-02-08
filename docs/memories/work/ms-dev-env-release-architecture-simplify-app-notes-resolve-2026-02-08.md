## Goal

Remove CLI-only dependency injection from `resolve_app_publish_notes`.

`ms/cli/commands/release_app_commands.py` currently passes `load_external_notes_file` into `ms/release/flow/app_publish.py::resolve_app_publish_notes`. This indirection adds no value because the flow layer already depends on infra/workflows.

## Scope

- `ms/release/flow/app_publish.py::resolve_app_publish_notes`
- `ms/cli/commands/release_app_commands.py`

## Definition of Done

- `uv run pytest` passes.
- `MS_ARCH_CHECKS=1 uv run pytest ms/test/architecture` passes.
- `uv run ruff check .` passes.
- `uv run pyright` passes.

## Progress Tracker

Legend: [ ] pending, [x] done

- [x] 1. Make `resolve_app_publish_notes` call `load_external_notes_file` directly
- [x] 2. Update CLI call site and imports
- [x] 3. Validate
- [ ] 4. Commit + PR
