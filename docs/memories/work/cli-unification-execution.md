# CLI Unification - Execution Runbook (DEV Priority)

> Date: 2026-01-25
> Status: ACTIVE (source of truth for implementation order)
> Scope: DEV only. END-USER is explicitly deferred.

This document is the **precise step-by-step** execution plan to make `ms/` the **only** system.
No legacy, no duplication, no ambiguous entrypoints.


## Target UX/DX (DEV)

- Canonical invocation (no activation required): `uv run ms <cmd>`
- One mental model:
  - `ms setup` prepares everything.
  - `ms check` diagnoses and gives actionable hints.
  - `ms build/upload/run/web` operate on codebases.
- Idempotent: rerun is safe.
- Non-invasive: no shell profile edits by default.
- Repro-friendly: tool versions are pinned; repo SHAs are snapshotted.


## Non-negotiable rules

- One backend: all business logic lives in `ms/`.
- One state directory: `.ms/` (gitignored).
- One build directory: `.build/` (gitignored).
- One toolchain directory: `tools/` (gitignored).
- Workspace detection uses `.ms-workspace` marker.
- On Windows, bridge build requires: `rustup` + MSVC Build Tools + Windows SDK (no full IDE).


## Workspace layout (DEV)

- `.ms-workspace` (marker, versioned)
- `.ms/` (state, locks, caches)
  - `.ms/state.toml`
  - `.ms/repos.lock.json`
  - `.ms/cache/downloads/`
  - `.ms/platformio/` (PLATFORMIO_CORE_DIR)
  - `.ms/platformio-cache/` (PLATFORMIO_CACHE_DIR)
  - `.ms/platformio-build-cache/` (PLATFORMIO_BUILD_CACHE_DIR)
- `tools/` (toolchains + wrappers)
  - `tools/bin/` (wrappers)
  - `tools/state.json` (installed versions)
  - `tools/platformio/venv/` (dedicated PlatformIO venv)
- `.build/` (build outputs)
- `bin/` (runtime artifacts like built bridge binary)


## Entry point policy

- Documented, official: `uv run ms ...`
- Optional convenience: `tools/activate.*` to add `tools/bin` to PATH.
- No repo-level wrapper (`commands/ms`) in the final system.


## Toolchain reproducibility policy

- Tool versions are pinned in a versioned file (planned: `ms/data/toolchains.toml`).
- `ms tools sync` installs exactly those versions.
- `ms tools upgrade` is the only command that updates pins (and should be committed).


## Repo reproducibility policy

- Default: follow each repo's **default branch** at latest HEAD.
- Always write `.ms/repos.lock.json` with resolved `head_sha`.
- Future (optional): `ms repos sync --lock <file>` to reproduce exact SHAs.


## PlatformIO policy (official)

PlatformIO is isolated to the workspace using official env vars:
- `PLATFORMIO_CORE_DIR=<workspace>/.ms/platformio`
- `PLATFORMIO_CACHE_DIR=<workspace>/.ms/platformio-cache`
- `PLATFORMIO_BUILD_CACHE_DIR=<workspace>/.ms/platformio-build-cache`

PlatformIO is installed into a dedicated venv:
- `tools/platformio/venv`

Wrappers in `tools/bin` force these env vars for all PlatformIO invocations.


## Implementation milestones (strict order)

### Milestone 1 - CLI skeleton (already started)

Deliverables:
- `python -m ms --help` works
- `ms check` implemented in `ms/` (no ms_cli)


### Milestone 2 - `ms repos sync` (clone all repos via gh)

Command:
- `uv run ms repos sync`

Behavior (exact):
1) Require `gh` present and authenticated (`gh auth status`)
2) For each org in:
   - `open-control`
   - `petitechose-midi-studio`
   run `gh repo list <org> --limit <N> --json name,isArchived,defaultBranchRef,url --jq ...`
3) Filter out `isArchived=true`
4) Clone via HTTPS:
   - if `<workspace>/<group>/<repo>/.git` absent -> `git clone <url> <dest>`
   - else -> `git fetch` and if clean -> `git pull --ff-only`
5) Write `.ms/repos.lock.json` with:
   - org, repo, default_branch, head_sha, url
6) Never reset dirty repos; log warning and skip.

Acceptance:
- Fresh workspace clone + `ms repos sync` yields `open-control/*` and `midi-studio/*` trees.


### Milestone 3 - `ms tools sync` (install pinned toolchains)

Command:
- `uv run ms tools sync`

Behavior (exact):
1) Read pinned versions from `ms/data/toolchains.toml`
2) Use `.ms/cache/downloads` for all downloads
3) Install tools into `tools/<tool-id>`
4) Record installed versions into `tools/state.json`
5) Generate wrappers into `tools/bin`
6) Generate activation scripts: `tools/activate.sh`, `tools/activate.ps1`, `tools/activate.bat`

Acceptance:
- `ms check` reports toolchain OK after `ms tools sync`.


### Milestone 4 - PlatformIO venv + workspace core_dir

Commands:
- `uv run ms tools sync` (includes PlatformIO)

Behavior (exact):
1) Create `tools/platformio/venv` if missing
2) Install pinned `platformio==<version>` into that venv
3) Create wrappers `tools/bin/pio` and `tools/bin/platformio` that set:
   - `PLATFORMIO_*` directories to `.ms/*`
4) Ensure `ms` passes these env vars when calling OpenControl scripts.

Acceptance:
- PlatformIO does not touch `~/.platformio` by default.
- `pio system info` works under workspace isolation.


### Milestone 5 - `ms setup --mode dev` (orchestrator)

Command:
- `uv run ms setup --mode dev`

Behavior (exact):
1) Create/Update `.ms/state.toml` (mode=dev)
2) Run `ms repos sync`
3) Run `ms tools sync`
4) Run `uv sync --frozen --extra dev`
5) Run `ms check`

Flags:
- `--skip-repos`, `--skip-tools`, `--skip-python`, `--skip-check`
- `--dry-run` (prints actions, does not modify)

Acceptance:
- On a fresh clone, `ms setup --mode dev` completes and `ms check` is actionable.


### Milestone 6 - Bridge (required) and Bitwig (optional)

- `uv run ms bridge build`
- `uv run ms bitwig deploy`

Behavior (exact):
- Windows prereqs are detected and reported before attempting build.


### Milestone 7 - Final switch + legacy removal

1) Switch entrypoint in `pyproject.toml`:
   - `ms = "ms.cli.app:main"`
2) Remove `ms_cli/` directory
3) Remove `commands/` and any repo-level wrappers
4) Keep at most a minimal bootstrap script (optional) that only checks `uv` is installed, then runs `uv run ms setup`.

Acceptance:
- No references to `ms_cli` remain.
- One documented entrypoint.
