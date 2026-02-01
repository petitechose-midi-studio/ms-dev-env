# Phase 02b: Maintainer Release Command (ms release publish)

Status: DONE

## Goal

Add a maintainer-only release command in `ms-dev-env` (the `ms` CLI) that:

- lets maintainers select the exact repo commits (SHAs) to build for a release
- proposes a safe next version/tag (SemVer, monotone; no rollback by accident)
- generates a `release-specs/<tag>.json` in `petitechose-midi-studio/distribution`
- optionally adds `release-notes/<tag>.md` for richer release notes
- opens + merges the PR in `distribution` and dispatches the `Publish` workflow
- stops before the final approval gate (environment `release` approval remains manual)

This phase is about *release operator safety* and *repeatability*.

## Context / Constraints

- `ms-dev-env` is public and dev-only. The release command must not rely on secrets.
- Authorization is enforced by GitHub:
  - only users with `WRITE/MAINTAIN/ADMIN` on `petitechose-midi-studio/distribution` can merge/spec/publish
  - stable/beta signing requires manual approval of the `release` environment
- Org policy currently blocks GitHub Actions from creating PRs. Therefore:
  - channel pointers are not updated by CI
  - v1 client strategy is: stable uses GitHub Releases `latest`; rollback lists releases via GitHub Releases API

## CLI Contract (v1)

Subcommands (non-monolithic API surface):

1) `ms release plan`
- No side effects.
- Produces a fully resolved release plan (channel, tag, SHAs, spec/notes paths).
- Suitable for contributors to propose a release plan in an issue without publishing.
- Can export a plan JSON via `--out <path>`.

2) `ms release prepare`
- Creates/updates the distribution PR:
  - writes `release-specs/<tag>.json`
  - writes `release-notes/<tag>.md` (optional)
  - opens a PR
- Does not run the publish workflow unless explicitly requested.
- Can consume a previously exported plan via `--plan <path>`.

3) `ms release publish`
- Ensures the spec exists on `distribution/main`.
- Dispatches the `Publish` workflow in `petitechose-midi-studio/distribution`.
- Does **not** approve the `release` environment.
- Optionally watches the run and prints the Release URL.
- Can consume a previously exported plan via `--plan <path>`.

4) `ms release remove`
- Deletes one or more distribution test releases (PR-cleanup of artifacts + GitHub Release deletion).
- Must be explicit and confirmable (irreversible part).
- Supports `--yes` for automation.

Common flags:
- `--channel stable|beta`
- `--bump major|minor|patch` (default: patch)
- `--tag vX.Y.Z[...]` (overrides bump; must satisfy monotonic rules)
- `--repo <id>=<sha>` (non-interactive override; repeatable)
- `--notes <text>` and/or `--notes-file <path.md>`
- `--dry-run` (prints actions; no git/gh mutations)
- `--out <plan.json>` (plan only)
- `--plan <plan.json>` (prepare/publish)

Interactive behavior (default):
- show the last N commits per repo and prompt selection
- show CI status per candidate commit (success/failed/unknown)
- present a final summary and require explicit confirmation (e.g. retype tag)

## Release Inputs (repos list)

The command uses a small config describing which repos are part of a release.

v1 required repos (matches `distribution/publish.yml` today):
- `loader` -> `petitechose-midi-studio/loader`
- `oc-bridge` -> `open-control/bridge`

Each repo entry records:
- `id` (matches `release-spec.json`)
- `repo` slug (`owner/name`)
- `ref` (typically `main`)
- `required_ci_workflow_file` (typically `.github/workflows/ci.yml`)

The config must be extensible (Phase 04/05 will add `ms-manager`, firmware, Bitwig extension).

## Versioning Rules (SemVer)

Stable tags:
- Format: `vMAJOR.MINOR.PATCH` (non-prerelease)

Beta tags:
- Format: `vMAJOR.MINOR.PATCH-beta.N` (prerelease)

Rules (must be enforced):
- No rollback by default:
  - new stable must be strictly greater than the latest stable
  - new beta base version must be >= next stable target
- Tag must not already exist.
- Default suggestion:
  - stable: increment PATCH +1
  - beta: same base as next stable, `beta.1` (or `beta.(N+1)` if already exists)

## CI Guardrail (per repo SHA)

Before accepting a selected SHA, the command must check CI status for the repo.

Policy (v1):
- Default: reject SHAs without a successful CI run.
- Allow override only with an explicit `--allow-non-green` flag.

Implementation (recommended):
- Use `gh run list --workflow <workflow_file> --commit <sha> --status success`.

## Distribution PR + Notes

Files written in `petitechose-midi-studio/distribution`:
- `release-specs/<tag>.json`
- `release-notes/<tag>.md` (optional)

Notes file structure (recommended):
- header (channel/tag/date)
- pinned SHAs (links per repo)
- user-provided markdown appended

Publish workflow integration (required):
- `publish.yml` must use `release-notes/<tag>.md` as `gh release create --notes-file` when present.

## Architecture (avoid monolith)

Add a dedicated package under `ms/services/release/`:

- `config.py`: distribution repo slug, release repos list, tag regexes, defaults.
- `model.py`: typed dataclasses (no `typing.Any`).
- `semver.py`: parse/compare tags, compute next tag.
- `gh.py`: wrapper around `gh` (uses `ms.platform.process.run`), plus JSON parsing via `ms.core.structured`.
- `ci.py`: check CI success for a repo+sha.
- `spec.py`: build and write `release-specs/<tag>.json`.
- `notes.py`: build and write `release-notes/<tag>.md`.
- `dist_repo.py`: ensure clone, ensure clean, create branch, commit, push, PR, merge.
- `workflow.py`: dispatch `Publish`, detect run URL, wait-for-approval status.
- `planner.py`: pure planning logic (no side effects); used by `ms release plan`.

CLI layer:
- `ms/cli/commands/release_cmd.py` with a Typer sub-app `release`.
- Minimal logic in CLI; all real logic in services.

## Security Model (ms-dev-env is public)

Threat model:
- A malicious PR could try to alter the maintainer command.

Mitigations:
- GitHub permission gating:
  - `ms release prepare/publish` must check `viewerPermission` on `petitechose-midi-studio/distribution` and refuse otherwise.
- No secrets in `ms-dev-env`.
- No shell evaluation (`subprocess.run([...])` only; no `shell=True`).
- Dry-run and explicit confirmation before side effects.
- Repo policy:
  - CODEOWNERS for `ms/cli/commands/release_*.py` and `ms/services/release/**`
  - branch protection for `ms-dev-env/main`

## Exit Criteria

- `ms release --help` documents plan/prepare/publish.
- `ms release plan` can generate a plan without side effects.
- `ms release prepare` creates a PR in `distribution` with spec (+ notes optional).
- `ms release publish` dispatches `Publish` and prints run URL.
- All default safety checks are enforced (permissions, monotone tag, tag-exists, CI green).
- Full test suite passes:
  - `uv run pyright`
  - `uv run pytest ms/test -q`

## Results (recorded)

Implemented in `ms-dev-env`:
- CLI:
  - `ms release plan`
  - `ms release prepare`
  - `ms release publish`
  - `ms release remove`
- Modules: `ms/services/release/*` (semver, planning, CI checks, spec/notes generation, dist PR, workflow dispatch)
- Guardrails:
  - permission gating via `viewerPermission` on `petitechose-midi-studio/distribution`
  - monotone tags enforced
  - CI green enforced by default; `--allow-non-green` explicit override
  - confirmation required before side effects (retype tag)

Additional features (post-MVP, now shipped):
- Plan file export/import:
  - `ms release plan --out plan.json`
  - `ms release prepare --plan plan.json`
  - `ms release publish --plan plan.json`
- Cleanup command:
  - `ms release remove --tag <tag> [--tag ...] [--ignore-missing] [--yes]`

Scope (v1):
- repos pinned: `loader`, `oc-bridge`
- firmware `.hex` selection/packaging is deferred (later phase)

Distribution integration:
- `petitechose-midi-studio/distribution` `publish.yml` uses `release-notes/<tag>.md` as the release body when present.

## Tests (complete coverage)

Unit tests (no network):
- SemVer parsing/comparison:
  - stable tags
  - beta tags
  - ignore non-matching tags (e.g. `v0.0.0-test.3`)
- Next tag proposal:
  - patch bump default
  - beta numbering
  - monotone enforcement
- Release spec generation:
  - required fields
  - deterministic formatting
- Notes generation:
  - includes pinned SHAs

Mocked integration tests (no network):
- `gh` wrapper parsing from fixtures:
  - commits listing
  - workflow runs listing
  - repo permission
  - release list
- CLI behavior:
  - `ms release plan --dry-run` returns 0 and prints summary
  - `ms release prepare --dry-run` does not write/commit/push
  - `ms release publish --dry-run` does not dispatch

Optional network tests (opt-in marker):
- Validate `ms release plan` against live GitHub endpoints.
- Validate CI status detection.

Regression tests (safety):
- Refuse to run publish if tag exists.
- Refuse to run prepare/publish without sufficient GitHub permission.
- Refuse non-green SHA unless `--allow-non-green`.
- `remove` refuses deleting stable tags unless `--force`.
