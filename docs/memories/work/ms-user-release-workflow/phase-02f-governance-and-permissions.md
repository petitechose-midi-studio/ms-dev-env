# Phase 02f: Governance, Permissions, and Safety

Status: DONE

## Goal

Be open to contributions while keeping control over:

- what gets merged to `main`
- what gets signed and published to end users

## Principle (LOCKED)

- Canonical end-user releases are published only from `petitechose-midi-studio/distribution`.
- The trust anchor is the signed `manifest.json` (ed25519) produced by distribution CI.
- Merge rights and release approval are separate roles.

## Roles

Organization: `petitechose-midi-studio`

- `maintainers`:
  - can merge to `main` (branch restrictions)
- `release-managers`:
  - can approve the distribution `release` environment (beta/stable signing)
- `contributors`:
  - intended for triage permissions (issues/PR support), without merge rights

## Distribution: Release Permissions

Environments:

- `release` (stable/beta):
  - required reviewers: `@petitechose-midi-studio/release-managers`
  - branch policy: `main` only
  - admin bypass: disabled
- `nightly`:
  - no reviewers (fully automated)
  - branch policy: `main` only
  - admin bypass: disabled

Rationale:

- only approved maintainers can produce signatures for end users
- nightly is auto, but still limited to `main` to avoid running on arbitrary branches

## Branch Protection (main)

We require CI to be green before merge, but we do not require PR approvals
by default (solo maintainer compatible).

All protected branches:

- force pushes: disabled
- deletions: disabled
- conversation resolution: required
- push restrictions: enabled (teams: `maintainers`)

Status checks:

- `distribution`: `test`
- `ms-dev-env`: `test (ubuntu-latest)`, `test (windows-latest)`, `test (macos-latest)`, `test (fedora)`
- `core`: `firmware (release)`
- `plugin-bitwig`: `firmware (release)`, `bwextension`
- `loader`: `test (ubuntu-latest)`, `test (windows-latest)`, `test (macos-latest)`

## CODEOWNERS

`distribution/.github/CODEOWNERS` exists to document ownership of release-critical paths.

Note: Code-owner review enforcement is intentionally not required by branch protection
until at least 2 maintainers exist (GitHub does not allow approving your own PR).

## ms Tooling Impact

- `ms release prepare/publish` merges distribution spec PRs.
- Since distribution main now requires CI status checks, `ms` waits for PR merge to land
  before dispatching `Publish`.

Operational note:

- `distribution` has auto-merge enabled so `ms` can use `gh pr merge --auto`.
