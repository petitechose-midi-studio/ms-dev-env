# Release Operations (Maintainers)

This is intentionally short.

Authoritative sources:

- CLI: `uv run ms --help`
- Workflows: `.github/workflows/*`

## Concepts

- End-user distribution lives in the dedicated repo `petitechose-midi-studio/distribution`.
- Channels: `stable`, `beta`.
- A release bundle is described by a signed manifest (hashes + pinned SHAs).
- Release dependency promotion is remote-first: local repositories are audited for unsafe
  states, but release BOM/pin SHAs are resolved from GitHub refs.

## Dependency Promotion Contract

`uv run ms release dependencies` is the supported path for promoting Core dependency pins.

The command first audits every repository in the dependency graph:

- dirty working trees block the release;
- detached heads block the release;
- missing upstreams, diverged branches, behind branches, and local `main` commits not present on
  `origin/main` block the release;
- non-canonical branches block the default release path until the dependency is merged and the
  workspace is switched back to the manifest branch.

Only after that audit passes does the command resolve release SHAs from GitHub. For the default
release path, the selected SHAs are the remote manifest branches, currently `origin/main`. The
generated OpenControl BOM and Core CI/runtime pins must therefore match what GitHub Actions can
fetch, not an uncommitted or branch-local workspace state.

Feature branches can still be used for development validation, but they are not promoted into
`core/main` by the default dependency release flow.

Release PR merges must respect GitHub branch protections. Repositories in the release graph keep
required status checks enabled and have `Allow auto-merge` enabled. The CLI requests
`gh pr merge --auto`. The release tooling must not fall back to a direct/admin merge when auto-merge
is unavailable. If GitHub cannot queue the PR, the command fails with the PR URL and the repository
setting that must be fixed.

While `petitechose-audio` is the only maintainer and the same identity authors release PRs, required
approving reviews are intentionally disabled on `main`: GitHub cannot usefully enforce self-review,
and requiring one would only force an admin bypass. The release safety contract is therefore:

- no dirty or divergent dependency workspace;
- release BOM/pins resolved from fetchable GitHub refs;
- required status checks green;
- PR-based merge through GitHub auto-merge.

If another maintainer joins, or if release PRs are authored by a separate release GitHub App, required
approving reviews can be re-enabled without changing the default release command. `ms release`
already treats review approval as conditional: if GitHub reports `REVIEW_REQUIRED`, the command
requires a valid approval from a different identity before the PR can merge.

`ms test ms-dev-env` is the local preflight for tooling changes. It enables the same strict
architecture checks that CI runs, so release tooling layering/import regressions fail locally before
the branch is pushed. The dedicated CI architecture job remains as the remote double-check.

For a fully unattended PR + terminal approval flow with required reviews enabled, the PR author and
approver must be separate GitHub identities. The target architecture is:

- the CLI pushes release branches, then a release GitHub App opens release PRs;
- the maintainer account approves from the terminal;
- GitHub auto-merges once required checks, and required reviews if enabled, are satisfied;
- interrupted releases are resumed by querying the open release PR.

Until that release App is available to the local CLI, `ms release` uses the authenticated `gh` user
for PR creation and can only approve PRs authored by another identity.

When a release GitHub App is configured, `ms release` opens release PRs through the App installation
token, then uses the active `gh` maintainer account to approve the PR if GitHub reports
`REVIEW_REQUIRED`, and finally queues `gh pr merge --auto`. Configure the App locally with
per-organization variables:

- `MS_RELEASE_GITHUB_APP_ID_OPEN_CONTROL`
- `MS_RELEASE_GITHUB_APP_PRIVATE_KEY_PATH_OPEN_CONTROL`
- `MS_RELEASE_GITHUB_APP_ID_PETITECHOSE_MIDI_STUDIO`
- `MS_RELEASE_GITHUB_APP_PRIVATE_KEY_PATH_PETITECHOSE_MIDI_STUDIO`

The unsuffixed `MS_RELEASE_GITHUB_APP_ID` and `MS_RELEASE_GITHUB_APP_PRIVATE_KEY_PATH` variables are
accepted as defaults, but per-organization values are preferred because the two GitHub organizations
can use separate private Apps. The App must be installed on the target repositories and must be able
to create pull requests. The maintainer account must remain a different identity from the App author.

## Typical commands

- Guided: `uv run ms release`
- Explicit:
  - `uv run ms release content plan|prepare|publish ...`
  - `uv run ms release app plan|prepare|publish ...`
  - `uv run ms release dependencies --dry-run`
  - `uv run ms release dependencies --promote --watch`

## Archived details

Detailed multi-phase release workflow documents are archived out of this repo to avoid drift and onboarding confusion.
