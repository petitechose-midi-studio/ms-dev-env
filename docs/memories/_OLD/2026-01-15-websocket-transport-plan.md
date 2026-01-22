# Plan : Communication Desktop/WASM via Protocol Bitwig

**Date :** 2026-01-15  
**Statut :** A implémenter  
**Contexte :** Permettre à plugin-bitwig de fonctionner sur Desktop/WASM avec le même code app

---

## 1. CONTEXTE & OBJECTIF

### 1.1 Architecture actuelle (Teensy uniquement)

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         TEENSY (plugin-bitwig)                          │
├─────────────────────────────────────────────────────────────────────────┤
│  BitwigContext                                                          │
│       │                                                                 │
│       ▼                                                                 │
│  BitwigProtocol ─────► IMessageTransport (interface)                   │
│       │                        │                                        │
│       │                        ▼                                        │
│       │                 USB Binary (hal-teensy)                         │
│       │                        │                                        │
│       │                        ▼                                        │
│       │                   oc-bridge                                    │
│       │                        │                                        │
│       │                        ▼                                        │
│       │                 Bitwig Extension                               │
└───────┴─────────────────────────────────────────────────────────────────┘
```

### 1.2 Architecture cible (Teensy + Desktop + WASM)

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    DESKTOP / WASM (plugin-bitwig)                       │
├─────────────────────────────────────────────────────────────────────────┤
│  BitwigContext  (INCHANGE)                                             │
│       │                                                                 │
│       ▼                                                                 │
│  BitwigProtocol (INCHANGE) ────► IMessageTransport (interface)         │
│                                          │                              │
│                    ┌─────────────────────┼─────────────────────┐       │
│                    │                     │                     │       │
│                Desktop                 WASM                 Teensy     │
│                    │                     │                     │       │
│                    ▼                     ▼                     ▼       │
│             UdpTransport        WebSocketTransport       USB Binary   │
│              (hal-net)            (hal-net) NEW         (hal-teensy)  │
│                    │                     │                     │       │
│                    └─────────────────────┼─────────────────────┘       │
│                                          ▼                              │
│                                     oc-bridge                          │
│                                          │                              │
│                                          ▼                              │
│                                   Bitwig Extension                     │
└─────────────────────────────────────────────────────────────────────────┘
```

**Principe clé : Le code app (BitwigContext, BitwigProtocol, handlers, views) reste IDENTIQUE.**

---

## 2. MODIFICATIONS FRAMEWORK

### 2.1 IMessageTransport - Extension de l'interface

**Fichier :** `open-control/framework/src/oc/hal/IMessageTransport.hpp`

**Changements :**

```cpp
class IMessageTransport {
public:
    // ═══════════════════════════════════════════════════════════════
    // EXISTANT (inchange)
    // ═══════════════════════════════════════════════════════════════
    virtual ~IMessageTransport() = default;
    virtual core::Result<void> init() = 0;
    virtual void update() = 0;
    virtual void send(const uint8_t* data, size_t length) = 0;
    
    using ReceiveCallback = std::function<void(const uint8_t* data, size_t len)>;
    virtual void setOnReceive(ReceiveCallback cb) = 0;

    // ═══════════════════════════════════════════════════════════════
    // NOUVEAU (optionnel, avec defaults pour retrocompat)
    // ═══════════════════════════════════════════════════════════════
    
    /// @brief Transport pret a envoyer/recevoir ?
    /// @return true si operationnel (default pour UDP, Serial)
    virtual bool isReady() const { return true; }
    
    /// @brief Callback quand l'etat ready change
    using ReadyCallback = std::function<void(bool ready)>;
    virtual void setOnReadyChanged(ReadyCallback cb) { (void)cb; }
};
```

**Justification :**
- `isReady()` : polling synchrone de l'etat
- `setOnReadyChanged()` : notification reactive (optionnel)
- Defaults = retrocompatibilite totale (UDP, Binary inchanges)

---

## 3. NOUVEAU : WebSocketTransport (hal-net)

### 3.1 API Emscripten WebSocket

**Header :** `<emscripten/websocket.h>`  
**Link :** `-lwebsocket.js`

**Fonctions principales :**
```cpp
// Creation
EMSCRIPTEN_WEBSOCKET_T emscripten_websocket_new(EmscriptenWebSocketCreateAttributes* attr);

// Envoi binaire
EMSCRIPTEN_RESULT emscripten_websocket_send_binary(socket, data, length);

// Callbacks (async, declenches par le navigateur)
emscripten_websocket_set_onopen_callback(socket, userData, callback);
emscripten_websocket_set_onmessage_callback(socket, userData, callback);
emscripten_websocket_set_onclose_callback(socket, userData, callback);
emscripten_websocket_set_onerror_callback(socket, userData, callback);

// Fermeture
emscripten_websocket_close(socket, code, reason);
emscripten_websocket_delete(socket);
```

**Etats WebSocket (standard W3C) :**
- 0: CONNECTING
- 1: OPEN
- 2: CLOSING
- 3: CLOSED

### 3.2 Header WebSocketTransport

**Fichier :** `open-control/hal-net/src/oc/hal/net/WebSocketTransport.hpp`

```cpp
#pragma once
#ifdef __EMSCRIPTEN__

#include <emscripten/websocket.h>
#include <oc/hal/IMessageTransport.hpp>
#include <oc/time/Time.hpp>
#include <string>
#include <vector>
#include <cstdint>

namespace oc::hal::net {

struct WebSocketConfig {
    /// URL du serveur WebSocket (oc-bridge)
    std::string url = "ws://127.0.0.1:9002";
    
    /// Reconnexion automatique
    bool autoReconnect = true;
    
    /// Delai initial entre tentatives (ms)
    uint32_t reconnectDelayMs = 1000;
    
    /// Delai max (backoff exponentiel)
    uint32_t reconnectMaxDelayMs = 30000;
    
    /// Limite de messages en attente (0 = illimite)
    size_t maxPendingMessages = 100;
};

class WebSocketTransport : public IMessageTransport {
public:
    explicit WebSocketTransport(const WebSocketConfig& config = {});
    ~WebSocketTransport() override;
    
    // Non-copyable, non-movable
    WebSocketTransport(const WebSocketTransport&) = delete;
    WebSocketTransport& operator=(const WebSocketTransport&) = delete;

    // ═══════════════════════════════════════════════════════════════
    // IMessageTransport
    // ═══════════════════════════════════════════════════════════════
    core::Result<void> init() override;
    void update() override;
    void send(const uint8_t* data, size_t length) override;
    void setOnReceive(ReceiveCallback cb) override;
    bool isReady() const override;
    void setOnReadyChanged(ReadyCallback cb) override;

private:
    enum class State { Disconnected, Connecting, Connected };
    
    // Emscripten callbacks (static, C-style)
    static EM_BOOL onOpen(int eventType, const EmscriptenWebSocketOpenEvent* e, void* userData);
    static EM_BOOL onMessage(int eventType, const EmscriptenWebSocketMessageEvent* e, void* userData);
    static EM_BOOL onClose(int eventType, const EmscriptenWebSocketCloseEvent* e, void* userData);
    static EM_BOOL onError(int eventType, const EmscriptenWebSocketErrorEvent* e, void* userData);
    
    void connect();
    void flushPendingMessages();
    void scheduleReconnect();
    
    WebSocketConfig config_;
    EMSCRIPTEN_WEBSOCKET_T socket_ = 0;
    State state_ = State::Disconnected;
    
    ReceiveCallback onReceive_;
    ReadyCallback onReadyChanged_;
    
    // Buffering
    std::vector<std::vector<uint8_t>> pendingMessages_;
    
    // Reconnection (utilise oc::time::millis())
    uint32_t lastAttemptMs_ = 0;
    uint32_t currentDelayMs_ = 0;
    uint32_t reconnectAttempts_ = 0;
};

}  // namespace oc::hal::net

#endif  // __EMSCRIPTEN__
```

### 3.3 Implementation WebSocketTransport

**Fichier :** `open-control/hal-net/src/oc/hal/net/WebSocketTransport.cpp`

```cpp
#ifdef __EMSCRIPTEN__

#include "WebSocketTransport.hpp"
#include <oc/log/Log.hpp>
#include <algorithm>

namespace oc::hal::net {

WebSocketTransport::WebSocketTransport(const WebSocketConfig& config)
    : config_(config)
    , currentDelayMs_(config.reconnectDelayMs) {}

WebSocketTransport::~WebSocketTransport() {
    if (socket_ > 0) {
        emscripten_websocket_close(socket_, 1000, "destructor");
        emscripten_websocket_delete(socket_);
    }
}

core::Result<void> WebSocketTransport::init() {
    if (!emscripten_websocket_is_supported()) {
        return core::err(core::ErrorCode::NOT_SUPPORTED);
    }
    connect();
    return core::ok();
}

void WebSocketTransport::connect() {
    EmscriptenWebSocketCreateAttributes attr;
    emscripten_websocket_init_create_attributes(&attr);
    attr.url = config_.url.c_str();
    attr.protocols = nullptr;  // Binary par defaut
    attr.createOnMainThread = true;  // Pour acces cross-thread si necessaire
    
    socket_ = emscripten_websocket_new(&attr);
    if (socket_ <= 0) {
        OC_LOG_ERROR("[WebSocket] Failed to create socket");
        scheduleReconnect();
        return;
    }
    
    state_ = State::Connecting;
    
    // Setup callbacks
    emscripten_websocket_set_onopen_callback(socket_, this, onOpen);
    emscripten_websocket_set_onmessage_callback(socket_, this, onMessage);
    emscripten_websocket_set_onclose_callback(socket_, this, onClose);
    emscripten_websocket_set_onerror_callback(socket_, this, onError);
}

void WebSocketTransport::update() {
    // Reconnection logic
    if (state_ == State::Disconnected && config_.autoReconnect) {
        uint32_t now = oc::time::millis();
        if (now - lastAttemptMs_ >= currentDelayMs_) {
            OC_LOG_INFO("[WebSocket] Attempting reconnect...");
            connect();
            lastAttemptMs_ = now;
        }
    }
}

void WebSocketTransport::send(const uint8_t* data, size_t length) {
    if (state_ == State::Connected) {
        emscripten_websocket_send_binary(socket_, const_cast<uint8_t*>(data), length);
    } else {
        // Buffer message
        if (config_.maxPendingMessages == 0 || 
            pendingMessages_.size() < config_.maxPendingMessages) {
            pendingMessages_.emplace_back(data, data + length);
        } else {
            // Drop oldest
            pendingMessages_.erase(pendingMessages_.begin());
            pendingMessages_.emplace_back(data, data + length);
            OC_LOG_WARN("[WebSocket] Buffer full, dropped oldest message");
        }
    }
}

void WebSocketTransport::setOnReceive(ReceiveCallback cb) {
    onReceive_ = std::move(cb);
}

bool WebSocketTransport::isReady() const {
    return state_ == State::Connected;
}

void WebSocketTransport::setOnReadyChanged(ReadyCallback cb) {
    onReadyChanged_ = std::move(cb);
}

void WebSocketTransport::flushPendingMessages() {
    for (const auto& msg : pendingMessages_) {
        emscripten_websocket_send_binary(socket_, 
            const_cast<uint8_t*>(msg.data()), msg.size());
    }
    pendingMessages_.clear();
}

void WebSocketTransport::scheduleReconnect() {
    if (!config_.autoReconnect) return;
    
    // Exponential backoff
    currentDelayMs_ = std::min(currentDelayMs_ * 2, config_.reconnectMaxDelayMs);
    lastAttemptMs_ = oc::time::millis();
    reconnectAttempts_++;
    
    OC_LOG_INFO("[WebSocket] Reconnect scheduled in {}ms (attempt {})", 
                currentDelayMs_, reconnectAttempts_);
}

// ═══════════════════════════════════════════════════════════════
// Static Emscripten Callbacks
// ═══════════════════════════════════════════════════════════════

EM_BOOL WebSocketTransport::onOpen(int, const EmscriptenWebSocketOpenEvent*, void* userData) {
    auto* self = static_cast<WebSocketTransport*>(userData);
    
    OC_LOG_INFO("[WebSocket] Connected");
    self->state_ = State::Connected;
    self->currentDelayMs_ = self->config_.reconnectDelayMs;  // Reset backoff
    self->reconnectAttempts_ = 0;
    
    self->flushPendingMessages();
    
    if (self->onReadyChanged_) {
        self->onReadyChanged_(true);
    }
    
    return EM_TRUE;
}

EM_BOOL WebSocketTransport::onMessage(int, const EmscriptenWebSocketMessageEvent* e, void* userData) {
    auto* self = static_cast<WebSocketTransport*>(userData);
    
    if (!e->isText && self->onReceive_) {
        self->onReceive_(e->data, e->numBytes);
    }
    
    return EM_TRUE;
}

EM_BOOL WebSocketTransport::onClose(int, const EmscriptenWebSocketCloseEvent* e, void* userData) {
    auto* self = static_cast<WebSocketTransport*>(userData);
    
    OC_LOG_WARN("[WebSocket] Closed (code={}, reason={})", e->code, e->reason);
    self->state_ = State::Disconnected;
    
    if (self->onReadyChanged_) {
        self->onReadyChanged_(false);
    }
    
    self->scheduleReconnect();
    
    return EM_TRUE;
}

EM_BOOL WebSocketTransport::onError(int, const EmscriptenWebSocketErrorEvent*, void* userData) {
    auto* self = static_cast<WebSocketTransport*>(userData);
    
    OC_LOG_ERROR("[WebSocket] Error occurred");
    // onClose sera appele ensuite par le navigateur
    
    return EM_TRUE;
}

}  // namespace oc::hal::net

#endif  // __EMSCRIPTEN__
```

### 3.4 Flux de donnees

**send() avec buffering :**
```
send(data, len)
    │
    ▼
┌─────────────────┐
│ isReady() ?     │
└────────┬────────┘
         │
    ┌────┴────┐
    │         │
   YES        NO
    │         │
    ▼         ▼
┌────────┐ ┌─────────────────────┐
│ Envoi  │ │ Buffer si < max     │
│ direct │ │ Sinon drop oldest   │
└────────┘ └─────────────────────┘
```

**Reconnexion dans update() :**
```
update()
    │
    ▼
┌──────────────────────────────┐
│ state_ == Disconnected ?     │
│ && autoReconnect             │
│ && millis() - lastAttempt    │
│    >= currentDelay           │
└──────────────┬───────────────┘
               │
              YES
               │
               ▼
        attemptConnect()
               │
               ▼
        currentDelay *= 2  (backoff)
        lastAttempt = millis()
```

---

## 4. BUILD PLUGIN-BITWIG POUR DESKTOP/WASM

### 4.1 Structure des fichiers

```
midi-studio/
├── plugin-bitwig/
│   ├── src/                    # Code partage (Teensy + Desktop + WASM)
│   │   ├── context/
│   │   ├── protocol/
│   │   ├── handler/
│   │   ├── state/
│   │   └── ui/
│   ├── platformio.ini          # Build Teensy existant
│   └── desktop/                # NOUVEAU
│       ├── main.cpp            # Entry point Desktop/WASM
│       ├── CMakeLists.txt      # Build native
│       └── wasm/
│           ├── CMakeLists.txt  # Build WASM
│           └── shell.html
```

### 4.2 main.cpp Desktop/WASM

**Fichier :** `plugin-bitwig/desktop/main.cpp`

```cpp
/**
 * @file main.cpp
 * @brief Desktop/WASM entry point for plugin-bitwig
 */

#define SDL_MAIN_HANDLED
#include <SDL2/SDL.h>
#include <memory>

#ifdef __EMSCRIPTEN__
    #include <emscripten.h>
    #include <oc/hal/net/WebSocketTransport.hpp>
#else
    #include <oc/hal/net/UdpTransport.hpp>
#endif

#include <oc/hal/sdl/Sdl.hpp>
#include <oc/hal/midi/LibreMidiTransport.hpp>
#include <oc/ui/lvgl/SdlBridge.hpp>
#include <lvgl.h>

#include <config/App.hpp>
#include "context/BitwigBootContext.hpp"
#include "context/BitwigContext.hpp"

// Application context for main loop
struct AppContext {
    oc::ui::lvgl::SdlBridge* bridge;
    oc::hal::sdl::InputMapper* input;
    oc::app::OpenControlApp* app;
    bool running;
};

static AppContext g_ctx;

void main_loop_iteration(void* arg) {
    AppContext* ctx = static_cast<AppContext*>(arg);
    
    SDL_Event event;
    while (SDL_PollEvent(&event)) {
        if (event.type == SDL_QUIT) {
            ctx->running = false;
#ifdef __EMSCRIPTEN__
            emscripten_cancel_main_loop();
#endif
            return;
        }
        ctx->input->handleEvent(event);
    }
    
    ctx->app->update();
    ctx->bridge->refresh();
}

int main(int argc, char* argv[]) {
    (void)argc; (void)argv;
    
    // SDL init
    SDL_Init(SDL_INIT_VIDEO | SDL_INIT_EVENTS);
    
    // LVGL + SDL Bridge
    static oc::ui::lvgl::SdlBridge bridge(
        320, 320,
        oc::hal::sdl::defaultTimeProvider,
        {.windowTitle = "Bitwig Controller", .createInputDevices = true}
    );
    bridge.init();
    
    // Input mapper
    static oc::hal::sdl::InputMapper input;
    // ... configure input mappings ...
    
    // Transport selon plateforme
#ifdef __EMSCRIPTEN__
    auto remoteTransport = std::make_unique<oc::hal::net::WebSocketTransport>(
        oc::hal::net::WebSocketConfig{.url = "ws://127.0.0.1:9002"}
    );
#else
    auto remoteTransport = std::make_unique<oc::hal::net::UdpTransport>(
        oc::hal::net::UdpConfig{.host = "127.0.0.1", .port = 9001}
    );
#endif

    // MIDI config
    oc::hal::midi::LibreMidiConfig midiConfig{
        .appName = "Bitwig Controller",
        .inputPortPattern = "IN [bitwig-desktop]",
        .outputPortPattern = "OUT [bitwig-desktop]"
    };

    // Build app
    static oc::app::OpenControlApp app = oc::hal::sdl::AppBuilder()
        .midi(std::make_unique<oc::hal::midi::LibreMidiTransport>(midiConfig))
        .remote(std::move(remoteTransport))
        .controllers(input)
        .inputConfig(Config::Input::CONFIG);

    // Register contexts
    app.registerContext<bitwig::BitwigBootContext>(0, "Boot");
    app.registerContext<bitwig::BitwigContext>(1, "Bitwig");
    app.begin();
    
    // Setup context
    g_ctx.bridge = &bridge;
    g_ctx.input = &input;
    g_ctx.app = &app;
    g_ctx.running = true;
    
#ifdef __EMSCRIPTEN__
    emscripten_set_main_loop_arg(main_loop_iteration, &g_ctx, -1, true);
#else
    while (g_ctx.running) {
        main_loop_iteration(&g_ctx);
        SDL_Delay(16);  // ~60 FPS
    }
    SDL_Quit();
#endif
    
    return 0;
}
```

### 4.3 CMakeLists.txt WASM

**Fichier :** `plugin-bitwig/desktop/wasm/CMakeLists.txt`

Modifications par rapport a core/desktop/wasm :
- Ajouter source `WebSocketTransport.cpp`
- Ajouter link `-lwebsocket.js`
- Inclure les sources plugin-bitwig (context, protocol, handler, state, ui)

```cmake
# Link flags additionnels
set(EMSCRIPTEN_LINK_FLAGS
    # ... existing flags ...
    "-lwebsocket.js"  # Pour WebSocketTransport
)
```

---

## 5. COTE OC-BRIDGE (etape suivante)

oc-bridge devra supporter WebSocket en plus de USB/UDP :

```
oc-bridge (a modifier)
├── USB Serial → Teensy
├── UDP Socket → Desktop native  (existant)
└── WebSocket Server → WASM      (NOUVEAU)
```

**Ports suggeres :**
- UDP : `9001` (existant)
- WebSocket : `9002` (nouveau)

---

## 6. PLAN D'IMPLEMENTATION

| # | Tache | Fichiers | Effort |
|---|-------|----------|--------|
| **1** | Etendre IMessageTransport | `framework/.../IMessageTransport.hpp` | 5 min |
| **2** | Creer WebSocketTransport | `hal-net/.../WebSocketTransport.hpp/cpp` | 1h |
| **3** | Ajouter `-lwebsocket.js` au CMake WASM | `wasm/CMakeLists.txt` | 5 min |
| **4** | Creer structure plugin-bitwig/desktop | Nouveau dossier + CMakeLists | 30 min |
| **5** | Creer main.cpp Desktop/WASM | `plugin-bitwig/desktop/main.cpp` | 30 min |
| **6** | Test build WASM | - | 15 min |
| **7** | Implementer WebSocket dans oc-bridge | Repo oc-bridge | Separe |

---

## 7. VERIFICATIONS DE FAISABILITE

| Point | Statut | Detail |
|-------|--------|--------|
| API Emscripten WebSocket | Verifie | `<emscripten/websocket.h>`, link `-lwebsocket.js` |
| Callbacks async | Gere | Via `onOpen/onMessage/onClose/onError` |
| Buffering pre-connexion | Concu | `pendingMessages_` avec limite configurable |
| Reconnexion auto | Concu | Backoff exponentiel dans `update()` |
| Timing | Utilise | `oc::time::millis()` du framework |
| Retrocompatibilite | Assuree | Defaults dans IMessageTransport |
| Code app inchange | Garanti | BitwigProtocol utilise IMessageTransport |

---

## 8. DECISIONS TECHNIQUES

| Question | Decision | Raison |
|----------|----------|--------|
| Signal ou callback pour etat ? | **Callback** | Garde interface pure, pas de dependance Signal |
| Buffer size ? | **Configurable** (default 100) | Flexibilite, drop oldest si plein |
| Messages a la reconnexion ? | **Flush** | Le protocole est stateless au niveau frame |
| Qui gere le timing ? | **`update()` + `oc::time::millis()`** | Utilise outils framework existants |
| UDP isReady() ? | **Toujours true** | UDP est connectionless |
| Naming methode remote | **`.remote()`** | Court, clair, pas de collision |

---

## 9. REFACTORING PREALABLE EFFECTUE

Avant ce plan, le refactoring suivant a ete realise :

### 9.1 Renommages
- `IFrameTransport` → `IMessageTransport`
- `UdpFrameTransport` → `UdpTransport`
- `UdpFrameConfig` → `UdpConfig`

### 9.2 Reorganisation modules
```
hal-desktop (supprime) → hal-sdl + hal-net + hal-midi

hal-sdl/   → SDL (InputMapper, SdlControllers, AppBuilder) - oc::hal::sdl
hal-net/   → Reseau (UdpTransport, futur WebSocketTransport) - oc::hal::net
hal-midi/  → MIDI (LibreMidiTransport) - oc::hal::midi
```

### 9.3 Decouplage AppBuilder
```cpp
// Avant (couple)
.midi({.appName = "...", ...})  // Dependait de LibreMidiConfig
.frames()                        // Dependait de UdpTransport

// Apres (decouple)
.midi(std::make_unique<LibreMidiTransport>(config))
.remote(std::make_unique<UdpTransport>(udpConfig))
```

---

## 10. FICHIERS A MODIFIER/CREER

### Framework (open-control)
- [ ] `framework/src/oc/hal/IMessageTransport.hpp` - Ajouter `isReady()`, `setOnReadyChanged()`

### hal-net (open-control)
- [ ] `hal-net/src/oc/hal/net/WebSocketTransport.hpp` - Nouveau
- [ ] `hal-net/src/oc/hal/net/WebSocketTransport.cpp` - Nouveau

### plugin-bitwig (midi-studio)
- [ ] `plugin-bitwig/desktop/` - Nouveau dossier
- [ ] `plugin-bitwig/desktop/main.cpp` - Entry point Desktop/WASM
- [ ] `plugin-bitwig/desktop/CMakeLists.txt` - Build native
- [ ] `plugin-bitwig/desktop/wasm/CMakeLists.txt` - Build WASM
- [ ] `plugin-bitwig/desktop/wasm/shell.html` - Template HTML

### oc-bridge (repo separe)
- [ ] Ajouter serveur WebSocket port 9002

---

## 11. TESTS

### 11.1 Tests unitaires
- [ ] `hal-net/test/test_WebSocketTransport.cpp` - Mock des callbacks Emscripten

### 11.2 Tests integration
1. Build WASM plugin-bitwig
2. Lancer oc-bridge avec WebSocket
3. Ouvrir dans navigateur
4. Verifier communication bidirectionnelle avec Bitwig

---

## 12. NOTES IMPORTANTES

1. **Emscripten WebSocket est event-driven** - Les callbacks sont appeles par le navigateur, pas par `update()`

2. **`update()` sert uniquement pour la reconnexion** - Pas pour lire les messages

3. **Buffer de messages** - Les messages envoyes avant connexion sont bufferises et envoyes a la connexion

4. **Backoff exponentiel** - Evite de spammer le serveur en cas de probleme reseau

5. **`createOnMainThread = true`** - Necessaire pour que le WebSocket survive aux changements de contexte WASM
