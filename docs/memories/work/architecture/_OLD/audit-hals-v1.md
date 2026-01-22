# Audit Architectural - HALs Open Control v1

> Analyse des Hardware Abstraction Layers
> Date: 2026-01-21
> Scope: 5 packages HAL (hal-teensy, hal-sdl, hal-net, hal-common, hal-midi)

---

## Score Global HALs: 4.5/5 ⭐⭐⭐⭐⭐

| Package | Fichiers | Score | Commentaire |
|---------|----------|-------|-------------|
| hal-teensy | 17 | 4.5/5 | Cohérent, bien structuré |
| hal-sdl | 8 | 4.5/5 | Pattern InputMapper élégant |
| hal-net | 4 | 5/5 | Minimaliste, cross-platform |
| hal-common | 4 | 5/5 | Types partagés bien définis |
| hal-midi | 2 | 4.5/5 | Abstraction libremidi propre |

---

## 1. Vue d'Ensemble des HALs

### Architecture Multi-HAL

```
┌─────────────────────────────────────────────────────────────┐
│                     framework (interfaces)                   │
│  IButton, IEncoder, IMidi, IStorage, ITransport, IGpio      │
└─────────────────────────────────────────────────────────────┘
         ▲              ▲              ▲              ▲
         │              │              │              │
┌────────┴───┐  ┌───────┴───┐  ┌───────┴───┐  ┌──────┴────┐
│ hal-teensy │  │  hal-sdl  │  │  hal-net  │  │ hal-midi  │
│  (Teensy)  │  │ (Desktop) │  │  (WASM)   │  │ (Desktop) │
└────────────┘  └───────────┘  └───────────┘  └───────────┘
         │              │
         └──────┬───────┘
                ▼
        ┌──────────────┐
        │  hal-common  │
        │ (types/defs) │
        └──────────────┘
```

---

## 2. hal-teensy (Embedded)

### Structure

```
hal-teensy/src/oc/hal/teensy/
├── Teensy.hpp              # Convenience header
├── AppBuilder.hpp          # Builder fluent Teensy-specific
├── ButtonController.hpp    # IButton impl (template)
├── EncoderController.hpp   # IEncoder impl (template)
├── EncoderToolHardware.hpp # IEncoderHardware impl
├── TeensyGpio.hpp          # IGpio impl (singleton)
├── GenericMux.hpp          # IMultiplexer impl (template)
├── UsbMidi.hpp/cpp         # IMidi impl
├── UsbSerial.hpp           # ITransport impl
├── EEPROMBackend.hpp       # IStorage impl
├── LittleFSBackend.hpp     # IStorage impl
├── SDCardBackend.hpp       # IStorage impl
├── Ili9341.hpp/cpp         # IDisplay impl
└── TeensyOutput.hpp        # Log output
```

### Points Forts

1. **AppBuilder Teensy-specific** avec conversion implicite
   ```cpp
   app = oc::hal::teensy::AppBuilder()
       .midi()
       .encoders(Config::ENCODERS)
       .buttons(Config::BUTTONS);  // Pas de .build() nécessaire
   ```

2. **Templates pour taille fixe** (embedded-friendly)
   ```cpp
   template <size_t N>
   class ButtonController : public interface::IButton { ... }
   ```

3. **Injection GPIO** via singleton
   ```cpp
   inline TeensyGpio& gpio() {
       static TeensyGpio instance;
       return instance;
   }
   ```

4. **Factory helpers** pour création simplifiée
   ```cpp
   auto encoders = teensy::makeEncoderController(Config::Enc::ALL);
   auto buttons = teensy::makeButtonController(Config::Btn::ALL);
   ```

### Implémentation des Interfaces

| Interface | Implémentation | Retour init() |
|-----------|----------------|---------------|
| IButton | ButtonController<N> | `Result<void>` ✅ |
| IEncoder | EncoderController<N> | `Result<void>` ✅ |
| IEncoderHardware | EncoderToolHardware | `Result<void>` ✅ |
| IMidi | UsbMidi | `Result<void>` ✅ |
| ITransport | UsbSerial | `Result<void>` ✅ |
| IStorage | EEPROMBackend | `bool` ⚠️ |
| IStorage | LittleFSBackend | `bool` ⚠️ |
| IStorage | SDCardBackend | `bool` ⚠️ |
| IDisplay | Ili9341 | `Result<void>` ✅ |
| IGpio | TeensyGpio | N/A |
| IMultiplexer | GenericMux<N> | `Result<void>` ✅ |

### Violations Identifiées

1. **IStorage::begin() → bool** (incohérent avec framework)
   - `EEPROMBackend::begin()` → `bool`
   - `LittleFSBackend::begin()` → `bool`
   - `SDCardBackend::begin()` → `bool`

---

## 3. hal-sdl (Desktop Simulation)

### Structure

```
hal-sdl/src/oc/hal/sdl/
├── Sdl.hpp                  # Convenience header
├── AppBuilder.hpp           # Builder fluent SDL-specific
├── SdlButtonController.hpp  # IButton impl (event-driven)
├── SdlEncoderController.hpp # IEncoder impl (event-driven)
├── InputMapper.hpp/cpp      # SDL event → HAL events
├── SdlTime.hpp              # Time provider (SDL_GetTicks)
└── SdlOutput.hpp            # Log output (std::cout)
```

### Points Forts

1. **InputMapper élégant** - Fluent API pour mapping souris/clavier
   ```cpp
   InputMapper input;
   input.button(SDLK_SPACE, ButtonID::PLAY)
        .encoderRing(100, 100, 40, 20, EncoderID::VOL, 100.0f)
        .encoderWheel(200, 100, 30, EncoderID::PAN, 0.02f);
   ```

2. **Event-driven** (pas de polling)
   ```cpp
   void update(uint32_t) override {
       // No-op: SDL is event-driven, not polled
   }
   ```

3. **Feedback callbacks** pour sync visuel
   ```cpp
   input.setButtonFeedback([](ButtonID id, bool pressed) { ... });
   input.setEncoderFeedback([](EncoderID id, float value) { ... });
   ```

4. **Injection MIDI** découplée
   ```cpp
   // hal-sdl ne dépend PAS de hal-midi
   .midi(std::make_unique<LibreMidiTransport>(config))  // Injecté par l'app
   ```

### Implémentation des Interfaces

| Interface | Implémentation | Retour init() |
|-----------|----------------|---------------|
| IButton | SdlButtonController | `Result<void>` ✅ |
| IEncoder | SdlEncoderController | `Result<void>` ✅ |

### Observations

- **Pas de IStorage** dans hal-sdl (utilise filesystem natif via app)
- **NullMidi** utilisable si pas de MIDI réel nécessaire
- **Lifetime contract** documenté pour InputMapper

---

## 4. hal-net (Network Transports)

### Structure

```
hal-net/src/oc/hal/net/
├── UdpTransport.hpp/cpp       # ITransport impl (Desktop)
└── WebSocketTransport.hpp/cpp # ITransport impl (Emscripten)
```

### Points Forts

1. **Cross-platform UDP** (Windows/Linux/macOS)
   ```cpp
   #ifdef _WIN32
       SOCKET socket_ = INVALID_SOCKET;
   #else
       int socket_ = -1;
   #endif
   ```

2. **WebSocket avec reconnexion automatique**
   ```cpp
   struct WebSocketConfig {
       bool autoReconnect = true;
       uint32_t reconnectDelayMs = 1000;
       uint32_t reconnectMaxDelayMs = 30000;  // Exponential backoff cap
   };
   ```

3. **Message buffering** pendant déconnexion
   ```cpp
   std::vector<std::vector<uint8_t>> pendingMessages_;
   ```

### Implémentation des Interfaces

| Interface | Implémentation | Retour init() |
|-----------|----------------|---------------|
| ITransport | UdpTransport | `Result<void>` ✅ |
| ITransport | WebSocketTransport | `Result<void>` ✅ |

---

## 5. hal-common (Types Partagés)

### Structure

```
hal-common/src/oc/hal/common/embedded/
├── ButtonDef.hpp   # Configuration bouton hardware
├── EncoderDef.hpp  # Configuration encodeur hardware
├── GpioPin.hpp     # Source GPIO (MCU/MUX)
└── Types.hpp       # Alias types (ButtonID, EncoderID)
```

### Points Forts

1. **Support enum class** pour IDs type-safe
   ```cpp
   template <typename EnumT,
             typename = std::enable_if_t<std::is_enum_v<EnumT> &&
                                         std::is_same_v<std::underlying_type_t<EnumT>, uint16_t>>>
   constexpr ButtonDef(EnumT id_, GpioPin pin_, bool activeLow_ = true)
   ```

2. **Constexpr** pour tables de configuration compile-time
   ```cpp
   constexpr ButtonDef buttons[] = {
       {ButtonID::PLAY, {9, Source::MUX}, true},
   };
   ```

3. **Documentation claire** des paramètres (ppr, rangeAngle, etc.)

---

## 6. hal-midi (Desktop MIDI)

### Structure

```
hal-midi/src/oc/hal/midi/
└── LibreMidiTransport.hpp/cpp  # IMidi impl (libremidi)
```

### Points Forts

1. **libremidi abstraction** (WinMM, ALSA, CoreMIDI, WebMIDI)
2. **Port pattern matching** pour auto-connexion
   ```cpp
   struct LibreMidiConfig {
       std::string inputPortPattern = "";   // Empty = first available
       std::string outputPortPattern = "";
   };
   ```
3. **Active notes tracking** pour `allNotesOff()`

### Implémentation des Interfaces

| Interface | Implémentation | Retour init() |
|-----------|----------------|---------------|
| IMidi | LibreMidiTransport | `Result<void>` ✅ |

---

## 7. Cohérence Inter-HAL

### Pattern AppBuilder Uniforme

| HAL | AppBuilder | Conversion Implicite | Time Provider |
|-----|------------|---------------------|---------------|
| hal-teensy | `teensy::AppBuilder` | ✅ | `millis()` |
| hal-sdl | `sdl::AppBuilder` | ✅ | `SDL_GetTicks()` |

### Cohérence Result<void> vs bool

| Interface | Attendu | hal-teensy | hal-sdl | hal-net | hal-midi |
|-----------|---------|------------|---------|---------|----------|
| IButton::init() | `Result<void>` | ✅ | ✅ | N/A | N/A |
| IEncoder::init() | `Result<void>` | ✅ | ✅ | N/A | N/A |
| IMidi::init() | `Result<void>` | ✅ | N/A | N/A | ✅ |
| ITransport::init() | `Result<void>` | ✅ | N/A | ✅ | N/A |
| **IStorage::begin()** | **`bool`** | **⚠️ bool** | N/A | N/A | N/A |

**Observation:** La violation `IStorage::begin() → bool` est dans le **framework** (IStorage.hpp), pas dans les HALs. Les HALs implémentent correctement l'interface telle qu'elle est définie.

---

## 8. Dépendances Inter-HAL

```
hal-teensy ──────────► hal-common
                          ▲
hal-sdl ─────────────────┘ (indirect via app)

hal-net ────────────────► (aucune dépendance HAL)

hal-midi ───────────────► (aucune dépendance HAL)
```

**Observation:** Les HALs sont bien découplés. Seul `hal-teensy` dépend directement de `hal-common` pour les types `ButtonDef`/`EncoderDef`.

---

## 9. Recommandations

### Priorité Haute

| # | Action | Impact |
|---|--------|--------|
| 1 | Corriger `IStorage::begin() → init()` dans **framework** | Cohérence API |

### Priorité Moyenne

| # | Action | Impact |
|---|--------|--------|
| 2 | Documenter architecture multi-HAL dans README principal | Clarté contributeurs |
| 3 | Ajouter hal-sdl storage backend (fichier JSON local) | Simulation complète |

### Priorité Basse

| # | Action | Impact |
|---|--------|--------|
| 4 | Unifier namespace `oc::hal::*` vs `oc::hal::common::embedded::*` | Lisibilité |

---

## 10. Conclusion

Les HALs sont de **très bonne qualité** avec une architecture cohérente:

**Points forts:**
- Pattern AppBuilder uniforme entre Teensy et SDL
- Découplage excellent (hal-midi indépendant de hal-sdl)
- Support cross-platform propre (hal-net)
- Types partagés avec support enum class (hal-common)

**Point d'amélioration principal:**
- La violation `IStorage::begin() → bool` vient du **framework**, pas des HALs

**Verdict:** Les HALs respectent bien les principes de cohérence et d'extensibilité. Un nouveau HAL (ex: hal-rpi pour Raspberry Pi) pourrait être ajouté en suivant le pattern établi.

---

*Audit consolidé - Framework + HALs = Architecture Open Control complète*
