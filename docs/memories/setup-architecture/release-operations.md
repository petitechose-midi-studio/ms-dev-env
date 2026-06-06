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

Release PR merges must respect GitHub branch protections. Repositories in the release graph have
`Allow auto-merge` enabled, and the CLI requests `gh pr merge --auto`. The release tooling must not
fall back to a direct/admin merge when auto-merge is unavailable. If GitHub cannot queue the PR, the
command fails with the PR URL and the repository setting that must be fixed.

For a fully unattended PR + terminal approval flow, the PR author and approver must be separate
GitHub identities. The target architecture is:

- a release GitHub App creates/pushes release branches and opens PRs;
- the maintainer account approves from the terminal;
- GitHub auto-merges once required checks and reviews are satisfied;
- interrupted releases are resumed by querying the open release PR.

Until that release App is available to the local CLI, `ms release` uses the authenticated `gh` user
for PR creation and can only approve PRs authored by another identity.

## Typical commands

- Guided: `uv run ms release`
- Explicit:
  - `uv run ms release content plan|prepare|publish ...`
  - `uv run ms release app plan|prepare|publish ...`
  - `uv run ms release dependencies --dry-run`
  - `uv run ms release dependencies --promote --watch`

## Archived details

Detailed multi-phase release workflow documents are archived out of this repo to avoid drift and onboarding confusion.
