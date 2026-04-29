# ms-dev-env

Developer workspace for MIDI Studio (core + bitwig) and OpenControl.

This repo provides a single CLI, `ms`, that can:

- bootstrap a dev machine (minimal prerequisites + bundled toolchains)
- sync all required git repos into `open-control/` and `midi-studio/`
- build and run the native simulators (Windows/macOS/Linux)
- build and serve the WASM simulators (browser)
- run unit tests through the workspace CMake/CTest path
- build/upload/monitor Teensy firmware (PlatformIO)

The end-user distribution/installer is tracked separately (see roadmap).

## Release Role

- `ms-dev-env` is the maintainer and orchestration workspace.
- It provides the `ms` CLI used to prepare release inputs, verify candidate state, and orchestrate
  controlled release publication.
- It is not an end-user release surface and does not publish product binaries as a standalone
  product repo.
- Producer repos publish signed candidates for their own artifact families. End-user payload
  publication remains centered on `petitechose-midi-studio/distribution`.

## Quickstart (dev)

Prerequisite to *run* the CLI: `uv`.

1) Install `uv`

- https://docs.astral.sh/uv/getting-started/installation/

2) Get the workspace

- If you already have `git`:

```bash
git clone https://github.com/petitechose-midi-studio/ms-dev-env
cd ms-dev-env
```

- If you don't have `git` yet: download the ZIP from GitHub, extract it, then run the commands below.

3) One command setup

```bash
uv run ms setup --yes
```

What it does:

- checks and installs a small allowlisted set of system prerequisites when possible
- syncs repos (`open-control/*`, `midi-studio/*`) and toolchains (`tools/`)
- installs a prebuilt `oc-bridge` into `bin/bridge/`
- syncs Python deps (`uv sync --frozen --extra dev`)
- runs `ms check`

## Common commands

```bash
# List apps
uv run ms list

# Build simulators
uv run ms build core --target native
uv run ms build bitwig --target native

# Run simulators
uv run ms run core
uv run ms run bitwig

# WASM (build + serve)
uv run ms web core
uv run ms web bitwig

# Unit tests (unified Python/Rust/Node/CMake workflow)
uv run ms test
uv run ms test env
uv run ms test app
uv run ms test firmware
uv run ms test ms-manager-svelte
uv run ms test ms-manager-tauri
uv run ms test core
uv run ms test all

# Note: `ms run` / `ms web` auto-start a headless `oc-bridge` (dev) using `config.toml` ports.
# For WASM, use the printed URL (it includes `bridgeWsPort=...`).

# Teensy firmware (PlatformIO env defaults to last build or platformio.ini default_envs)
uv run ms build core --target teensy
uv run ms upload core --env dev
uv run ms monitor core --env dev

# Bridge (installs prebuilt if needed, then runs)
uv run ms bridge

 # Workspace health + repo status
 uv run ms check
 uv run ms status

 # Maintainer: sync all repos (includes ms-manager + distribution + examples)
 uv run ms sync --repos --profile maintainer
```

Optional: install user-level `ms`/`oc-*` launchers bound to this workspace:

```bash
uv run ms setup --yes --install-cli --update-shell --remember-workspace
```

After that you can run `ms ...` from anywhere. The launcher delegates to
`uv run --project <this-workspace>`, so it uses the repo environment instead of
a separate `uv tool` environment.

## System dependencies (native builds)

`ms` can guide installation (`uv run ms prereqs --install`) but some deps are OS packages.

Linux (Ubuntu/Debian):

```bash
sudo apt-get update
sudo apt-get install -y build-essential pkg-config libsdl2-dev libasound2-dev libudev-dev
```

Linux (Fedora):

```bash
sudo dnf install -y gcc gcc-c++ pkgconf-pkg-config SDL2-devel alsa-lib-devel systemd-devel
```

macOS:

```bash
xcode-select --install
```

SDL2 is optional on macOS (the build can fetch it as a fallback).

Windows:

- Native builds (core/bitwig simulators) use bundled Zig + Ninja (no system GCC required).
- Unit tests use `uv run ms test ...` as the unified local path for Python, Rust, Node, and CMake targets.

Notes:

- Virtual MIDI:
  - Windows: install loopMIDI (https://www.tobias-erichsen.de/software/loopmidi.html)
  - macOS: enable IAC Driver in Audio MIDI Setup
  - Linux: `snd-virmidi` (see `uv run ms check` hints)

## Roadmap

- Internal work notes live in `docs/memories/`.
- Distribution (stable/beta) + end-user installer plan: `docs/memories/setup-architecture/README.md`
