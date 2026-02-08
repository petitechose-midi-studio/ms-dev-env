## Goal

Remove "stringly-typed" prepare outcomes in release flows (where a field named `pr_url` sometimes contains a non-URL like `"(already merged) ..."`).

Replace those ambiguous strings with a small typed model that preserves the exact console output but makes the code explicit.

## Scope

- Introduce a typed PR outcome (merged PR vs already merged / already present).
- Update prepare flows:
  - `ms/release/flow/content_prepare.py::prepare_distribution_pr`
  - `ms/release/flow/app_prepare.py::prepare_app_pr`
- Update dependent flows + call sites:
  - CLI: `ms/cli/commands/release_content_commands.py`, `ms/cli/commands/release_app_commands.py`
  - Guided: `ms/release/flow/guided/content_steps.py`, `ms/release/flow/guided/app_steps.py`
  - Guided adapters: `ms/cli/release_guided_content.py`, `ms/cli/release_guided_app.py`
  - Tests: `ms/test/cli/test_release_guided_flows.py`

## Non-goals

- No change to the text displayed to users (keep "PR merged: ..." and existing labels).
- No change to GitHub/Git behavior.

## Definition of Done

- `uv run pytest` passes.
- `MS_ARCH_CHECKS=1 uv run pytest ms/test/architecture` passes.
- `uv run ruff check .` passes.
- `uv run pyright` passes.

## Progress Tracker

Legend: [ ] pending, [x] done, [~] in progress

- [x] 1. Add typed PR outcome model in release flow layer
- [x] 2. Update `prepare_distribution_pr` to return typed outcome
- [x] 3. Update `prepare_app_pr` to return typed outcome
- [x] 4. Update CLI + guided flows call sites to print typed outcome
- [x] 5. Update tests/mocks
- [x] 6. Validate (pytest + arch + ruff + pyright)

## Notes

Current ambiguity locations:

- `ms/release/flow/content_prepare.py`: returns `"(already merged) {plan.spec_path}"` as a fake PR URL.
- `ms/release/flow/app_prepare.py`: returns `AppPrepareResult(pr_url=f"(already merged) {tag}")`.

## What Changed (Executed)

- Added typed outcome model: `ms/release/flow/pr_outcome.py` (`PrMergeOutcome`).
- Prepare steps now return typed outcomes:
  - `ms/release/flow/content_prepare.py::prepare_distribution_pr` -> `Result[PrMergeOutcome, ReleaseError]`
  - `ms/release/flow/app_prepare.py::prepare_app_pr` -> `Result[AppPrepareResult, ReleaseError]` where `AppPrepareResult.pr: PrMergeOutcome`
- Propagated into prepared outputs:
  - `ms/release/flow/content_prepare.py::PreparedContentRelease.pr`
  - `ms/release/flow/app_prepare.py::PreparedAppRelease.pr`
- Updated call sites (prints stay identical because `PrMergeOutcome.__str__` returns the same label/url):
  - `ms/cli/commands/release_content_commands.py`
  - `ms/cli/commands/release_app_commands.py`
  - `ms/release/flow/guided/content_steps.py`
  - `ms/release/flow/guided/app_steps.py`
  - `ms/cli/release_guided_content.py`
  - `ms/test/cli/test_release_guided_flows.py`

## Verification

```bash
uv run pytest
MS_ARCH_CHECKS=1 uv run pytest ms/test/architecture
uv run ruff check .
uv run pyright
```

Results: all green.
