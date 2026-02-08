## Goal

Remove "shape duplication" in `ms/release/view/*` by replacing large `Protocol` mirrors with canonical shared dataclasses in the release domain.

This targets readability + SOLID (explicit contracts) + KISS (fewer layers of indirection).

## Scope

- Move data-only models so `view` can import them without violating layering:
  - `RepoReadiness` (currently in `ms/release/resolve/auto/diagnostics.py`)
  - `AutoSuggestion` (currently in `ms/release/resolve/auto/carry_mode.py`)
  - Open-control preflight report models (currently in `ms/release/infra/open_control.py`)
- Update producers (resolve/infra) to use moved models.
- Update consumers (view + guided) to accept concrete types instead of `Protocol` mirrors.
- No behavior changes; output text stays identical.

## Definition of Done

- `uv run pytest` passes.
- `MS_ARCH_CHECKS=1 uv run pytest ms/test/architecture` passes.
- `uv run ruff check .` passes.
- `uv run pyright` passes.

## Progress Tracker

Legend: [ ] pending, [x] done, [~] in progress

- [x] 1. Create canonical models:
  - `ms/release/domain/diagnostics.py`
  - `ms/release/domain/open_control_models.py`
- [x] 2. Update producers:
  - `ms/release/resolve/auto/diagnostics.py`
  - `ms/release/resolve/auto/carry_mode.py`
  - `ms/release/resolve/auto/smart.py`
  - `ms/release/infra/open_control.py`
- [x] 3. Update consumers:
  - `ms/release/view/content_console.py`
  - `ms/release/view/app_console.py`
  - `ms/release/flow/guided/content_steps.py`
  - `ms/cli/release_guided_content.py`
- [x] 4. Remove now-unneeded Protocol mirrors in view modules
- [x] 5. Validate (pytest + arch + ruff + pyright)
- [x] 6. Record final state + follow-ups

## Follow-ups (Not in Scope)

- Consider moving URL helpers (`_gh_*_url`) into a dedicated `ms/release/view/urls.py` if duplication appears.
- Consider introducing a small `ReleasePreflightViewModel` if the console views keep growing.

## What Changed (Executed)

- Canonical models added:
  - `ms/release/domain/diagnostics.py` (`RepoReadiness`, `AutoSuggestion`)
  - `ms/release/domain/open_control_models.py` (open-control preflight report dataclasses)
- Producers updated to use canonical models:
  - `ms/release/resolve/auto/diagnostics.py` (moved `RepoReadiness` out of resolve)
  - `ms/release/resolve/auto/carry_mode.py` (moved `AutoSuggestion` out of resolve)
  - `ms/release/resolve/auto/smart.py` (imports adjusted)
  - `ms/release/infra/open_control.py` (moved report dataclasses out of infra)
- Consumers updated:
  - `ms/release/view/content_console.py` no longer defines large `Protocol` mirrors; it consumes the canonical models
  - `ms/release/view/app_console.py` now consumes `RepoReadiness` directly (keeps a small notes `Protocol`)
  - `ms/release/flow/guided/content_steps.py` now types open-control preflight as `OpenControlPreflightReport`
  - `ms/cli/release_guided_content.py` imports `OpenControlPreflightReport` from the domain

- Additional view-facing model cleanup:
  - `ms/release/domain/notes.py` introduced `AppPublishNotes`
  - `ms/release/flow/app_publish.py` now returns the domain `AppPublishNotes`
  - `ms/release/view/app_console.py` now consumes `AppPublishNotes` directly (removes the last notes `Protocol` mirror)

## Verification

```bash
uv run pytest
MS_ARCH_CHECKS=1 uv run pytest ms/test/architecture
uv run ruff check .
uv run pyright
```

Results: all green.
