## Goal

Make app planning consistent with content planning by returning a concrete plan dataclass (`AppReleasePlan`) from `plan_app_release` (instead of a raw `(tag, version)` tuple).

This reduces duplication (the wrapper `build_app_release_plan` was reconstructing the plan) and improves readability/contracts.

## Scope

- Change `ms/release/flow/app_plan.py::plan_app_release` to return `Result[AppReleasePlan, ReleaseError]`.
- Simplify `ms/release/flow/app_plan.py::build_app_release_plan` accordingly.
- Update guided + CLI + tests that depended on the tuple signature.

## Definition of Done

- `uv run pytest` passes.
- `MS_ARCH_CHECKS=1 uv run pytest ms/test/architecture` passes.
- `uv run ruff check .` passes.
- `uv run pyright` passes.

## Progress Tracker

Legend: [ ] pending, [x] done, [~] in progress

- [x] 1. Update app plan API (`plan_app_release` returns `AppReleasePlan`)
- [x] 2. Update CLI call sites (`release_app_commands.py`)
- [x] 3. Update guided flow types + adapters (`app_steps.py`, `release_guided_app.py`)
- [x] 4. Update tests/mocks (`ms/test/cli/test_release_guided_flows.py`)
- [ ] 5. Validate + commit + push

## Verification

```bash
uv run pytest
MS_ARCH_CHECKS=1 uv run pytest ms/test/architecture
uv run ruff check .
uv run pyright
```

Results: all green.
