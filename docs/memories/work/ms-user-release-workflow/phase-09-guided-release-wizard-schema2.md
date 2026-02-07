# Phase 09: Guided Release Wizard + Schema V2 (No Legacy)

Status: ACTIVE PLAN

Date: 2026-02-07

## Objective

Replace manual/flag-heavy release execution with one guided command (`ms release`) that:

- fails fast on auth/permissions
- uses selector-only interaction (arrow keys + Enter) for release choices
- preserves choices while navigating back
- provides a summary screen where every point can be edited
- requires a final explicit `y/n` confirmation before execution
- freezes source SHA(s) so selected commits cannot be invalidated during process
- supports optional external markdown notes injected at top of final release notes

Current scope in implementation:

- app release flow (`ms-manager`) is guided, resumable, and immutable by selected SHA.
- content release flow is also guided with multi-repo SHA selection and resumable steps.

## Hard requirements (locked)

1) Plan format

- Only schema v2 is valid.
- Schema v1 is rejected; no compatibility mode.

2) Guided UX

- `ms release` starts the guided workflow directly.
- Maintainer does not type free-form values for normal flow.
- Commit selection is done via selector UI (arrows + Enter).
- Backspace returns to previous step and keeps prior selection.
- Summary screen allows editing any step and returns to summary.

3) Immutable provenance

- Once SHA is selected and confirmed, release uses immutable frozen SHA.
- No fallback to moving `main` head.

4) Notes policy

- Optional `--notes-file <path.md>` accepted.
- Notes snapshot is frozen in session state.
- Final GitHub release notes keep auto-notes; external notes are prepended on top.

## Architecture

### A) Wizard engine

New guided state machine:

- Product selection (`app` / `content`)
- Permission preflight
- Channel selection (`stable` / `beta`)
- Bump selection (`patch` / `minor` / `major`)
- Tag preview/validation
- Per-repo SHA selection (green commits only by default)
- Optional notes file intake (CLI option, snapshotted)
- Summary edit loop
- Final `y/n` confirmation
- Execute

Navigation behavior:

- Backspace on a step: previous step
- Enter: validate current selection and continue
- Summary row select: re-open specific step
- Returning from edited step lands back on summary

### B) Session state (resumable)

Persist state under `.ms/release/sessions/` with fields:

- `schema: 2`
- `release_id`
- current step id
- selected product/channel/bump/tag
- selected repo refs + SHAs
- notes snapshot (content + hash)
- execution checkpoint metadata

All steps before final confirmation are resumable.

### C) Schema v2 plan format

Plan schema v2 required fields:

- `schema: 2`
- `product`
- `channel`
- `tag`
- `repos[]` with `id`, `slug`, `ref`, `sha`

For app flow, `repos[]` includes only `ms-manager`.

### D) Immutable SHA execution

App flow freeze model:

1. select base SHA from selector
2. create release branch from selected base SHA
3. apply version bump commit on that branch
4. use that exact commit SHA as `source_sha` for candidate + promote

No substitution by `main` head after PR merge.

### E) External notes integration

`--notes-file` handling:

- validate file early (exists, readable, `.md`, non-empty)
- snapshot content + hash into session
- pass frozen markdown payload to app release workflow
- workflow prepends markdown to auto-generated release notes body

Output structure in final release body:

1. Maintainer notes section (external markdown)
2. separator
3. auto-generated notes

## Implementation steps

1) Introduce schema v2-only in plan IO

- Update plan writer/reader to enforce schema 2.
- Remove schema 1 acceptance.
- Add tests for strict rejection of schema 1.

2) Add guided wizard UI primitives

- Implement selector component with arrow + enter + backspace support.
- Add summary edit loop selector.

3) Add release session persistence

- Create session model + load/save helpers.
- Save after each step transition.

4) Wire `ms release` to guided flow

- Command entrypoint starts wizard when no subcommand is provided.
- Keep explicit subcommands available for engineering/debug only.

5) Freeze app release source SHA

- Prepare app branch from selected SHA.
- Capture release commit SHA.
- Publish candidate/release workflows from that SHA.

6) Add optional notes-file support

- CLI option on guided and publish paths.
- Snapshot notes in session.
- Pass to workflow dispatch.
- Update `ms-manager` release workflow to prepend notes above auto-notes.

7) Tests and validation

- unit tests: schema v2 parser/writer, session state transitions
- integration-style tests: guided flow state machine step transitions
- smoke: release app dry-run from guided path

## Done criteria

- `ms release` runs guided flow with selector-only choices.
- Backspace and summary edit loop work as specified.
- Schema v1 plans are rejected.
- Selected SHA remains immutable through publish dispatch.
- External notes appear at top of final release notes; auto-notes preserved below.
- CI and tests pass without warnings.
