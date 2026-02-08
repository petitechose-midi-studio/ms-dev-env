## Goal

Remove pure forwarder wrappers in the remove flow (`ms/release/flow/content_remove.py`) that only existed to inject functions from the CLI.

This keeps the public API surface smaller and improves readability.

## Scope

- Delete from `ms/release/flow/content_remove.py`:
  - `resolve_remove_tags`
  - `remove_content_release_artifacts`
  - `remove_content_github_releases`
- Update CLI caller:
  - `ms/cli/commands/release_content_commands.py`

## Definition of Done

- `uv run pytest` passes.
- `MS_ARCH_CHECKS=1 uv run pytest ms/test/architecture` passes.
- `uv run ruff check .` passes.
- `uv run pyright` passes.

## Progress Tracker

Legend: [ ] pending, [x] done

- [x] 1. Remove forwarder wrappers
- [x] 2. Update CLI caller
- [x] 3. Validate
- [ ] 4. Commit + PR
