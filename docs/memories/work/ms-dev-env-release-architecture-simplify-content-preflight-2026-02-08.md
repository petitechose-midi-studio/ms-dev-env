## Goal

Simplify content preflight helpers by removing CLI-only dependency injection.

- `collect_release_preflight_issues` should be a concrete helper returning `RepoReadiness`.
- `load_open_control_report` should call `preflight_open_control` directly.

## Scope

- `ms/release/flow/content_preflight.py`
- `ms/cli/commands/release_content_commands.py`

## Definition of Done

- `uv run pytest` passes.
- `MS_ARCH_CHECKS=1 uv run pytest ms/test/architecture` passes.
- `uv run ruff check .` passes.
- `uv run pyright` passes.

## Progress Tracker

Legend: [ ] pending, [x] done

- [x] 1. Replace generic/injected preflight APIs with concrete ones
- [x] 2. Update CLI call sites
- [x] 3. Validate
- [ ] 4. Commit + PR
