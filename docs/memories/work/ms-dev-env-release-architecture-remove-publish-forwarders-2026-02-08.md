## Goal

Remove pure forwarder publish wrappers in the release flow layer.

Specifically:

- `ms/release/flow/content_publish.py::publish_content_release`
- `ms/release/flow/app_publish.py::publish_app_release_workflows`

These functions only forward arguments to the real publish functions and add no value.

## Scope

- Delete the forwarder functions.
- Update CLI callers to call canonical publish functions directly.
- Keep behavior unchanged.

## Definition of Done

- `uv run pytest` passes.
- `MS_ARCH_CHECKS=1 uv run pytest ms/test/architecture` passes.
- `uv run ruff check .` passes.
- `uv run pyright` passes.

## Progress Tracker

Legend: [ ] pending, [x] done

- [x] 1. Remove forwarder wrappers
- [x] 2. Update CLI callers
- [x] 3. Validate
- [ ] 4. Commit + PR
