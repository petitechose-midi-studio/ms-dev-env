# Release Operations (Maintainers)

This is intentionally short.

Authoritative sources:

- CLI: `uv run ms --help`
- Workflows: `.github/workflows/*`

## Concepts

- End-user distribution lives in the dedicated repo `petitechose-midi-studio/distribution`.
- Channels: `stable`, `beta`, `nightly`.
- A release bundle is described by a signed manifest (hashes + pinned SHAs).

## Typical commands

- Guided: `uv run ms release`
- Explicit:
  - `uv run ms release content plan|prepare|publish ...`
  - `uv run ms release app plan|prepare|publish ...`

## Archived details

Detailed multi-phase release workflow documents are archived out of this repo to avoid drift and onboarding confusion.
