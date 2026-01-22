# Refactor: Dev CLI DX Max (ms + setup)

**Scope**: workspace tooling + open-control + midi-studio
**Status**: started
**Created**: 2026-01-22
**Updated**: 2026-01-22 (session 2)

## Objective

Turn setup + CLI into a dev environment that is:

- reliable (reproducible, idempotent)
- safe (no implicit destructive actions)
- always up to date (via an explicit command)
- low friction (doctor, guided errors, progress)

## Decisions (locked)

- Windows dev shell: Git Bash (not PowerShell-first).
- `ms` is Python.
- Python unified on 3.13+ via `uv`.
- Policy safe:
  - `setup.sh` installs missing only (no upgrades, no `git pull`, no builds).
  - `ms update` is the only command that upgrades tools/deps and can `git pull` (only if worktree clean).
- Bridge is built from source (Rust stable).
- PlatformIO is required; install per PlatformIO official guidance (installer script / isolated env).
- Docs:
  - new user docs: `docs/ms-cli/`
  - existing internal docs: `docs/memories/`
- Java/Maven are portable tools in `tools/`.
- JDK: install JDK 25 (LTS) but compile Bitwig extension with Java 21 compatibility (`--release 21`).
- Icons/assets:
  - single builder: `open-control/ui-lvgl-cli-tools/icon/build.py`
  - svg->font pipeline uses `lv_font_conv@1.5.3`
  - JS runtime: Bun preferred (`bunx`), Node fallback
  - Inkscape + FontForge are system deps (guided by `ms doctor`)

## Roadmap

Each step must be:

- implemented in order
- validated with explicit checks
- logged (see `docs/memories/work/refactor-all-dev-cli-dx-max/NOTES.md`)

### Step 0 - Docs structure (done)

- [x] Move existing docs into `docs/memories/` (git mv)
- [x] Create `docs/ms-cli/`
- [x] Create this roadmap

Validation:

- `git status` shows moves, no missing docs

### Step 1 - CLI contract/spec (done)

- Define final command surface + aliases
- Define invariants (safe/update/build-only)
- Define exit codes + `--json` outputs

Validation:

- Spec exists in `docs/ms-cli/` and matches implementation plan

### Step 2 - Bootstrap safe (setup.sh) (done)

- Remove all builds from `setup.sh`
- No sudo by default (MIDI becomes an explicit fix)
- Install missing portable tools (uv+py313, cmake/ninja/zig, bun, emsdk, jdk25, maven)
- Install PlatformIO using official installer script if missing
- Shell config: PATH + completions

Validation:

- `bash -n setup.sh`
- Run `./setup.sh` twice (idempotent)

Status:

- Completed on Linux with `./setup.sh --skip-repos --skip-shell` and a second idempotency run.

### Step 3 - Python ms foundation (done)

- Implement `ms` python package + `commands/ms` launcher
- `config.toml` parsing
- progress/errors framework
- completions commands

Validation:

- `ms --help` works
- `ms completion --help` works

Status:

- Implemented a new Python `ms` CLI (delegating run/web/build/upload/monitor/clean/list to legacy).
- Added `pyproject.toml` + `uv.lock` and synced deps into `.venv`.
- Added `config.toml` and a minimal TOML loader.

### Step 4 - ms doctor (done)

- comprehensive diagnostics + guided fixes

Validation:

- `ms doctor` runs clean on a configured machine

Status:

- Implemented a comprehensive `ms doctor` with guided hints (tools, workspace, project, runtime, assets, system deps).

### Step 5 - ms verify (done)

- smoke tests + `--full` option

Validation:

- `ms verify` covers tool versions + key file presence

Status:

- Implemented `ms verify` smoke tests (tools + config + python deps sync + emsdk + PlatformIO).

### Step 6 - ms update (done)

- explicit tool upgrades + optional repo pulls (clean only)

Validation:

- `ms update` produces a deterministic summary of changes

Status:

- Implemented `ms update` with flags: `--repos`, `--tools`, `--python`, `--dry-run`.
- Tools refresh uses a safe backup under `tools/.old/<timestamp>/` then re-runs `./setup.sh --skip-repos --skip-shell`.

### Step 7 - ms setup (done)

- build bridge (cargo)
- build/deploy Bitwig extension (maven, release=21)

Validation:

- `ms setup` completes without manual intervention (except system deps like Inkscape/FontForge)

Status:

- Implemented `ms setup` to build `open-control/bridge` (cargo release) and Bitwig host extension (mvn + deploy).

### Step 8 - Assets/icons full featured (done)

- unify builder + config keys (HEADER_FILENAME, NAMESPACE)
- update wrappers
- bunx/npx fallback

Validation:

- icon generation runs and errors are guided when system deps are missing

Status:

- Updated `open-control/ui-lvgl-cli-tools/icon/build.py` to support:
  - `HEADER_FILENAME` + `NAMESPACE`
  - platform-specific `INKSCAPE_*` / `FONTFORGE_*`
  - `bunx` preferred for `lv_font_conv` (version pinned)
- Updated midi-studio icon configs + wrappers, and added `ms icons`.

### Step 9 - User docs (done)

- write `docs/ms-cli/*` pages

Validation:

- docs match commands and are copy/paste runnable

Status:

- Added initial user docs under `docs/ms-cli/`.

### Step 10 - Manual test matrix (in progress)

- Linux + macOS + Windows (Git Bash)

Validation:

- checklist complete

Status:

- Linux: validated (bootstrap, doctor, verify, update, setup).
- macOS: pending.
- Windows (Git Bash): pending.

### Step 11 - Bridge service parity (done)

- Ensure oc-bridge service logs are available in TUI on all platforms
- Ensure daemon mode broadcasts logs (service -> TUI)
- Add `ms bridge` wrapper command

Validation:

- Run `oc-bridge --daemon` and verify UDP log broadcast is working
- Run `ms bridge` and verify it launches oc-bridge

Status:

- Linux: daemon now broadcasts logs to UDP (`log_broadcast_port`) and monitoring listens on that port.
- Windows: service broadcaster now uses `log_broadcast_port`.
- Added `ms bridge` pass-through.

### Step 12 - Shortcuts (done)

- Add `core-dev` and `bitwig-dev` wrappers (including `bitwig-dev monitor`)

Validation:

- `bitwig-dev --help`
- `bitwig-dev monitor --help`

Status:

- Added `commands/bitwig-dev` and `commands/core-dev`.

### Step 13 - SDL entrypoint refactor + WASM MIDI (done)

- Factor SDL main loop boilerplate into shared helpers
- Add WASM MIDI port selector UI (In/Out dropdowns)
- Fix Bitwig extension Bridge Mode preference persistence

Validation:

- `ms web bitwig` shows MIDI selector, persists selection across reloads
- `ms run bitwig` communicates with Bitwig (native) after selecting "Native Sim (9001)" in Bitwig prefs
- Firefox WASM works with VirMIDI ports

Status:

- Added `midi-studio/core/sdl/entry/` helpers (MidiDefaults, SdlRunLoop, WasmArgs)
- Refactored core + bitwig entrypoints to use shared helpers
- Added MIDI selector UI in WASM shell.html with localStorage persistence
- Changed Bitwig extension from number slider to enum dropdown (fixes persistence)
- Fixed `workspace/config.toml` port convention (wasm = 9002)

### Step 14 - Push all repos (pending)

- Push all diverged repos to origin

Validation:

- `ms status` shows 0 diverged repos
