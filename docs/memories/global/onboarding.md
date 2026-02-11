# Onboarding (Start Here)

Goal: get a new dev productive in ~30 minutes.

## 1) What is this repo?

`ms-dev-env` is the workspace/orchestrator repo. It pins and manages multiple git repos under one folder so you can build/run:

- OpenControl (framework/runtime): `open-control/*`
- MIDI Studio (product): `midi-studio/*`

Key product repos:

- `midi-studio/core` (standalone firmware + desktop sims)
- `midi-studio/plugin-bitwig` (Bitwig integration)
- `midi-studio/ui` (`ms-ui`, shared LVGL UI components)

See: `docs/memories/midi-studio/overview.md`

## 2) Setup + sanity check

- Setup: `uv run ms setup --yes`
- Verify: `uv run ms check`
- Multi-repo status: `uv run ms status`

Useful commands: `docs/memories/global/commands.md`

## 3) Run/build targets

- Native sims:
  - `uv run ms run core`
  - `uv run ms run bitwig`
- WASM sims:
  - `uv run ms web core`
  - `uv run ms web bitwig`
- Firmware builds (PlatformIO):
  - `cd midi-studio/core && pio run -e dev`
  - `cd midi-studio/plugin-bitwig && pio run -e dev`

## 4) How the app is structured (patterns)

- Architecture: Handlers -> State -> Views (reactive signals).
- Overlays: owned/managed via OverlayManager + scope/authority.

Core authoritative docs:

- `midi-studio/core/docs/INVARIANTS.md`
- `midi-studio/core/docs/HOW_TO_ADD_HANDLER.md`
- `midi-studio/core/docs/HOW_TO_ADD_VIEW.md`
- `midi-studio/core/docs/HOW_TO_ADD_OVERLAY.md`

Code style reference: `docs/memories/global/code-style.md`

## 5) Hardware + navigation conventions

- IDs: `docs/memories/midi-studio/hw-layout.md`
- Navigation contract: `docs/memories/midi-studio/hw-navigation.md`
- Sequencer mapping draft: `docs/memories/midi-studio/hw-sequencer.md`

## 6) Shared UI (`ms-ui`)

Shared LVGL components live in `midi-studio/ui` and are included via `<ms/ui/...>`.

See: `docs/memories/midi-studio/shared-ui-ms-ui.md`

## 7) What to work on next

Active work notes live in `docs/memories/work/`.

Index: `docs/memories/work/README.md`
