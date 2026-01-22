# Plugin-Bitwig WASM Port - Implementation Plan

## Overview

This document details the plan for porting `plugin-bitwig` to run in a web browser via WebAssembly (WASM). The key insight is that **business code stays identical** - only the transport layer changes per platform.

## Current Architecture

### Transport Abstraction: IFrameTransport

The open-control framework uses `IFrameTransport` as the core abstraction for frame-based communication:

```
open-control/framework/src/oc/hal/IFrameTransport.hpp
```

```cpp
class IFrameTransport {
public:
    virtual core::Result<void> init() = 0;
    virtual void update() = 0;  // Poll for incoming data
    virtual void send(const uint8_t* data, size_t length) = 0;
    virtual void setOnReceive(ReceiveCallback cb) = 0;
};
```

### Existing Transport Implementations

| Platform | Transport | File |
|----------|-----------|------|
| Teensy | UsbSerial | (embedded in firmware) |
| Desktop | UdpFrameTransport | `open-control/hal-desktop/src/oc/hal/desktop/UdpFrameTransport.hpp` |
| **WASM** | **WebSocketFrameTransport** | **TO CREATE** |

### BitwigProtocol is Transport-Agnostic

```
midi-studio/plugin-bitwig/src/protocol/BitwigProtocol.hpp
```

```cpp
class BitwigProtocol : public Protocol::ProtocolCallbacks {
public:
    explicit BitwigProtocol(oc::hal::IFrameTransport& transport)
        : transport_(transport) {
        transport_.setOnReceive([this](const uint8_t* data, size_t len) {
            dispatch(data, len);
        });
    }
    // ...
private:
    oc::hal::IFrameTransport& transport_;  // <-- Any transport works!
};
```

### Data Flow Architecture

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                              WASM (Browser)                                     │
│                                                                                 │
│  ┌─────────────────────────────────────────────────────────────────────────┐   │
│  │                        BitwigContext                                     │   │
│  │                              │                                           │   │
│  │                     ┌────────┴────────┐                                  │   │
│  │                     │  BitwigProtocol │                                  │   │
│  │                     │  (unchanged!)   │                                  │   │
│  │                     └────────┬────────┘                                  │   │
│  │                              │                                           │   │
│  │                     ┌────────┴────────┐                                  │   │
│  │                     │ IFrameTransport │◄──── Interface                   │   │
│  │                     └────────┬────────┘                                  │   │
│  │                              │                                           │   │
│  │              ┌───────────────┼───────────────┐                           │   │
│  │              ▼               ▼               ▼                           │   │
│  │     ┌─────────────┐  ┌─────────────┐  ┌──────────────────┐              │   │
│  │     │  UsbSerial  │  │UdpTransport │  │WebSocketTransport│ ◄── NEW      │   │
│  │     │  (Teensy)   │  │  (Desktop)  │  │     (WASM)       │              │   │
│  │     └──────┬──────┘  └──────┬──────┘  └────────┬─────────┘              │   │
│  └────────────┼────────────────┼─────────────────┼──────────────────────────┘   │
│               │                │                 │                               │
└───────────────┼────────────────┼─────────────────┼───────────────────────────────┘
                │                │                 │
                ▼                ▼                 ▼
         ┌───────────┐    ┌───────────┐    ┌─────────────────┐
         │   USB     │    │    UDP    │    │   WebSocket     │
         │  Cable    │    │   9001    │    │   ws://...      │
         └─────┬─────┘    └─────┬─────┘    └────────┬────────┘
               │                │                   │
               └────────────────┼───────────────────┘
                                ▼
                        ┌─────────────┐
                        │  oc-bridge  │
                        │   (Rust)    │
                        └──────┬──────┘
                               │ UDP 9000
                               ▼
                        ┌─────────────┐
                        │   Bitwig    │
                        │  Extension  │
                        └─────────────┘
```

## What Exists vs What's Missing

### Exists (Reusable As-Is)

| Component | Location | Notes |
|-----------|----------|-------|
| BitwigProtocol | `plugin-bitwig/src/protocol/BitwigProtocol.hpp` | Transport-agnostic |
| BitwigContext | `plugin-bitwig/src/context/BitwigContext.hpp` | Application logic |
| All views | `plugin-bitwig/src/view/` | LVGL UI |
| Protocol messages | `plugin-bitwig/src/protocol/*.hpp` | Message definitions |
| IFrameTransport | `open-control/framework/src/oc/hal/IFrameTransport.hpp` | Interface |
| LVGL, UI framework | `open-control/ui-lvgl/` | Already WASM-compatible |
| LibreMidiTransport | `open-control/hal-desktop/` | Already WASM-compatible (WebMIDI) |

### Missing (To Implement)

| Component | Effort | Notes |
|-----------|--------|-------|
| WebSocketFrameTransport | ~150 lines C++ | New transport for WASM |
| oc-bridge WebSocket transport | ~200 lines Rust | New transport type |
| plugin-bitwig WASM CMakeLists | ~100 lines | Build configuration |
| shell.html for plugin-bitwig | ~50 lines | HTML wrapper |

## Implementation Steps

### Step 1: WebSocketFrameTransport (C++)

Create: `open-control/hal-desktop/src/oc/hal/desktop/WebSocketFrameTransport.hpp`

```cpp
#pragma once

#ifdef __EMSCRIPTEN__

#include <emscripten/websocket.h>
#include <oc/hal/IFrameTransport.hpp>
#include <string>
#include <vector>

namespace oc::hal::desktop {

struct WebSocketConfig {
    std::string url = "ws://127.0.0.1:9002";  // oc-bridge WebSocket port
    size_t recvBufferSize = 4096;
};

class WebSocketFrameTransport : public hal::IFrameTransport {
public:
    WebSocketFrameTransport();
    explicit WebSocketFrameTransport(const WebSocketConfig& config);
    ~WebSocketFrameTransport() override;

    core::Result<void> init() override;
    void update() override;
    void send(const uint8_t* data, size_t length) override;
    void setOnReceive(ReceiveCallback cb) override;
    
    bool isReady() const { return connected_; }

private:
    static EM_BOOL onOpen(int eventType, const EmscriptenWebSocketOpenEvent* event, void* userData);
    static EM_BOOL onMessage(int eventType, const EmscriptenWebSocketMessageEvent* event, void* userData);
    static EM_BOOL onClose(int eventType, const EmscriptenWebSocketCloseEvent* event, void* userData);
    static EM_BOOL onError(int eventType, const EmscriptenWebSocketErrorEvent* event, void* userData);

    WebSocketConfig config_;
    ReceiveCallback onReceive_;
    EMSCRIPTEN_WEBSOCKET_T socket_ = 0;
    bool connected_ = false;
};

}  // namespace oc::hal::desktop

#endif  // __EMSCRIPTEN__
```

**Key points:**
- Uses Emscripten's WebSocket API (`emscripten/websocket.h`)
- Static callbacks with `void* userData` for C++ instance
- Binary messages (not text)
- Requires `-lwebsocket.js` linker flag

### Step 2: oc-bridge WebSocket Transport (Rust)

Create: `open-control/bridge/src/transport/websocket.rs`

```rust
//! WebSocket transport for WASM client communication
//!
//! Listens on a port for WebSocket connections from browser-based WASM apps.

use super::{Transport, TransportChannels};
use crate::error::Result;
use bytes::Bytes;
use futures_util::{SinkExt, StreamExt};
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::Arc;
use tokio::net::TcpListener;
use tokio::sync::mpsc;
use tokio_tungstenite::accept_async;

pub struct WebSocketTransport {
    port: u16,
}

impl WebSocketTransport {
    pub fn new(port: u16) -> Self {
        Self { port }
    }
}

impl Transport for WebSocketTransport {
    fn spawn(self, shutdown: Arc<AtomicBool>) -> Result<TransportChannels> {
        let (in_tx, in_rx) = mpsc::channel::<Bytes>(64);
        let (out_tx, mut out_rx) = mpsc::channel::<Bytes>(64);

        let port = self.port;
        
        tokio::spawn(async move {
            let listener = TcpListener::bind(format!("127.0.0.1:{}", port))
                .await
                .expect("Failed to bind WebSocket port");
            
            while !shutdown.load(Ordering::Relaxed) {
                if let Ok((stream, _)) = listener.accept().await {
                    let ws = accept_async(stream).await.expect("WS handshake failed");
                    let (mut ws_tx, mut ws_rx) = ws.split();
                    
                    let in_tx = in_tx.clone();
                    let shutdown_inner = shutdown.clone();
                    
                    // RX task
                    tokio::spawn(async move {
                        while !shutdown_inner.load(Ordering::Relaxed) {
                            if let Some(Ok(msg)) = ws_rx.next().await {
                                if msg.is_binary() {
                                    let _ = in_tx.send(Bytes::from(msg.into_data())).await;
                                }
                            }
                        }
                    });
                    
                    // TX task
                    while let Some(data) = out_rx.recv().await {
                        let _ = ws_tx.send(tokio_tungstenite::tungstenite::Message::Binary(data.to_vec())).await;
                    }
                }
            }
        });

        Ok(TransportChannels {
            rx: in_rx,
            tx: out_tx,
        })
    }
}
```

**Changes needed in oc-bridge:**
1. Add `tokio-tungstenite` to `Cargo.toml`
2. Add `pub mod websocket;` to `transport/mod.rs`
3. Add WebSocket config option to CLI/config
4. Wire up in main.rs similar to UDP transport

### Step 3: plugin-bitwig WASM CMakeLists.txt

Create: `midi-studio/plugin-bitwig/desktop/wasm/CMakeLists.txt`

Based on `midi-studio/core/desktop/wasm/CMakeLists.txt`, with these key differences:

```cmake
# Key additions for plugin-bitwig:
set(PLUGIN_BITWIG_ROOT "${CMAKE_SOURCE_DIR}/../..")

# Include WebSocketFrameTransport (WASM-only)
file(GLOB_RECURSE HAL_DESKTOP_SOURCES "${HAL_DESKTOP_DIR}/src/*.cpp")
list(FILTER HAL_DESKTOP_SOURCES EXCLUDE REGEX ".*UdpFrameTransport.*")
# WebSocketFrameTransport is conditionally compiled via #ifdef __EMSCRIPTEN__

# plugin-bitwig sources
file(GLOB_RECURSE PLUGIN_SOURCES "${PLUGIN_BITWIG_ROOT}/src/*.cpp")

# Emscripten link flags - add WebSocket support
set(EMSCRIPTEN_LINK_FLAGS
    # ... same as core ...
    "-lwebsocket.js"  # Enable WebSocket API
)
```

### Step 4: BitwigContext Configuration

The context configuration already supports different modes:

```cpp
// In main.cpp for WASM:
static ContextConfig makeConfig() {
    ContextConfig config;
    config.frames = true;  // Required for IFrameTransport
    return config;
}

// Transport selection:
#ifdef __EMSCRIPTEN__
    WebSocketConfig wsConfig;
    wsConfig.url = "ws://127.0.0.1:9002";
    WebSocketFrameTransport transport(wsConfig);
#else
    UdpFrameConfig udpConfig;
    udpConfig.port = 9001;
    UdpFrameTransport transport(udpConfig);
#endif
```

## oc-bridge Configuration

### New Config Option

```toml
# oc-bridge.toml
[virtual]
enabled = true
port = 9001        # UDP for desktop apps
websocket = 9002   # WebSocket for WASM apps (NEW)
```

### CLI Option

```
oc-bridge --mode virtual --websocket-port 9002
```

## Port Mapping

| Transport | Port | Direction | Usage |
|-----------|------|-----------|-------|
| UDP (Bitwig) | 9000 | Bitwig Extension -> oc-bridge | Existing |
| UDP (Desktop) | 9001 | Desktop app <-> oc-bridge | Existing |
| WebSocket | 9002 | WASM app <-> oc-bridge | NEW |

## Testing Strategy

1. **Unit tests** for WebSocketFrameTransport (mock WebSocket)
2. **Integration test**: WASM app -> oc-bridge -> mock Bitwig
3. **End-to-end test**: Full browser test with real Bitwig

## Build Commands

```bash
# Build oc-bridge with WebSocket support
cd open-control/bridge
cargo build --release

# Build plugin-bitwig WASM
cd midi-studio/plugin-bitwig/desktop/wasm
mkdir build && cd build
emcmake cmake ..
emmake make -j4

# Run oc-bridge with WebSocket
./oc-bridge --mode virtual --websocket-port 9002

# Serve WASM app (use any HTTP server)
python -m http.server 8080
# Open http://localhost:8080/plugin_bitwig_wasm.html
```

## Files to Create/Modify

### New Files

| File | Lines | Priority |
|------|-------|----------|
| `open-control/hal-desktop/src/oc/hal/desktop/WebSocketFrameTransport.hpp` | ~100 | P0 |
| `open-control/hal-desktop/src/oc/hal/desktop/WebSocketFrameTransport.cpp` | ~80 | P0 |
| `open-control/bridge/src/transport/websocket.rs` | ~150 | P0 |
| `midi-studio/plugin-bitwig/desktop/wasm/CMakeLists.txt` | ~200 | P0 |
| `midi-studio/plugin-bitwig/desktop/wasm/shell.html` | ~80 | P0 |
| `midi-studio/plugin-bitwig/desktop/main.cpp` (WASM-compatible) | ~150 | P1 |

### Modifications

| File | Change |
|------|--------|
| `open-control/bridge/Cargo.toml` | Add `tokio-tungstenite` |
| `open-control/bridge/src/transport/mod.rs` | Add `pub mod websocket;` |
| `open-control/bridge/src/config.rs` | Add WebSocket port config |
| `open-control/bridge/src/cli.rs` | Add --websocket-port flag |
| `open-control/bridge/src/main.rs` | Wire up WebSocket transport |

## Summary

The plugin-bitwig WASM port is **low-risk and high-leverage**:

1. **Business logic unchanged** - BitwigContext, BitwigProtocol, views all stay identical
2. **Only transport layer changes** - Implement `IFrameTransport` for WebSocket
3. **Bridge changes minimal** - Add one more transport type following existing patterns
4. **Proven architecture** - Same pattern as midi-studio/core WASM build

Total estimated effort: **2-3 days**
- Day 1: WebSocketFrameTransport (C++) + oc-bridge WebSocket (Rust)
- Day 2: CMakeLists.txt, shell.html, main.cpp
- Day 3: Testing, debugging, polish
