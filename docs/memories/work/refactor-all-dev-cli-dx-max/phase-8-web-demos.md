# Phase 8: Web demos (GitHub Pages + local bridge)

**Scope**: publish static WASM demos for `core` and `bitwig`
**Status**: started
**Created**: 2026-01-28
**Updated**: 2026-01-28

## Goal

Publish two static demo endpoints (always pointing to "latest"):

- `/demo/core/latest/`
- `/demo/bitwig/latest/`

The demos are meant to be **usable** (not just viewable): the browser simulator talks to a
locally running `oc-bridge` using WebSocket.

Note: repository migration will change the base URL.

## Architecture (facts)

### WASM simulators

- Build output for `ms build <app> --target wasm` is:
  - `bin/<app_id>/wasm/<exe_name>.html`
  - `bin/<app_id>/wasm/<exe_name>.js`
  - `bin/<app_id>/wasm/<exe_name>.wasm`

- `core` WASM remote transport:
  - `midi-studio/core/sdl/main-wasm.cpp` connects to `ws://localhost:8100`

- `bitwig` WASM remote transport:
  - `midi-studio/plugin-bitwig/sdl/main-wasm.cpp` connects to `ws://localhost:8101`

- The HTML/JS shell is static and shared:
  - `midi-studio/core/sdl/wasm/shell.html`

### oc-bridge

- `oc-bridge` provides a WebSocket server for browser/WASM clients.
- Default ports (convention):
  - controller WS: 8100 (core), 8101 (bitwig)
  - host UDP: 9000 (hardware), 9001 (native sim), 9002 (WASM sim)

## User requirements (to make the demo work)

### Browser demo (core or bitwig)

- Run `oc-bridge` locally and listen for the controller WebSocket port:
  - core: `8100`
  - bitwig: `8101`

- Browser permissions / security:
  - WebMIDI permission (the shell requests `requestMIDIAccess({ sysex: true })`).
  - WebSocket connection to `ws://localhost:8100/8101` from an HTTPS page must be allowed by the browser.
    This must be validated on real browsers (Chrome/Firefox).

### End-to-end with Bitwig

- Install the Bitwig extension (`.bwextension`).
- In Bitwig, select bridge mode: `WASM Sim (9002)`.
- Run `oc-bridge` so it forwards controller -> host UDP port `9002`.

## CI strategy

- Build native executables on all OS targets (value: runnable local simulator).
- Build WASM only once (Ubuntu) and deploy the static artifacts.

## Decisions

- Keep hosting static (GitHub Pages).
- Keep bridge local (no remote bridge).
- Keep `latest` stable URLs under `/demo/<app>/latest/`.

## Risks / notes

- Browsers may block `ws://` connections from HTTPS pages as mixed content.
  If that happens, we will need a follow-up design (e.g. local HTTP hosting via `ms web`,
  or a secure local proxy).

- `oc-bridge` currently binds the WebSocket server to `0.0.0.0`.
  Consider restricting to `127.0.0.1` later to avoid LAN exposure.

## Work log

- 2026-01-28: phase created (plan aligned; implementation started).

## Sources

- `midi-studio/core/sdl/main-wasm.cpp`
- `midi-studio/plugin-bitwig/sdl/main-wasm.cpp`
- `midi-studio/core/sdl/wasm/shell.html`
- `open-control/bridge/src/transport/websocket.rs`
- `open-control/bridge/src/constants.rs`
- `midi-studio/plugin-bitwig/host/src/midistudio/MidiStudioExtension.java`
