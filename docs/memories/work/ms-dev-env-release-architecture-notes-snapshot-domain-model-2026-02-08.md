## Goal

Eliminate duplicate "external notes snapshot" shapes by moving the canonical model to `ms/release/domain/notes.py` and removing `Protocol` mirrors in guided/flow layers.

## Scope

- Move `ExternalNotesSnapshot` from `ms/release/infra/artifacts/notes_writer.py` to `ms/release/domain/notes.py`.
- Update producers/consumers:
  - `ms/release/infra/artifacts/notes_writer.py`
  - `ms/release/flow/app_publish.py`
  - `ms/release/flow/guided/bootstrap.py`
- Keep behavior unchanged.

## Definition of Done

- `uv run pytest` passes.
- `MS_ARCH_CHECKS=1 uv run pytest ms/test/architecture` passes.
- `uv run ruff check .` passes.
- `uv run pyright` passes.

## Progress Tracker

Legend: [ ] pending, [x] done, [~] in progress

- [x] 1. Add `ExternalNotesSnapshot` to `ms/release/domain/notes.py`
- [x] 2. Update `notes_writer.py` to import it and stop defining it
- [x] 3. Remove Protocol mirrors and update typing in `bootstrap.py` + `app_publish.py`
- [ ] 4. Validate + commit + push

## Verification

```bash
uv run pytest
MS_ARCH_CHECKS=1 uv run pytest ms/test/architecture
uv run ruff check .
uv run pyright
```

Results: all green.
