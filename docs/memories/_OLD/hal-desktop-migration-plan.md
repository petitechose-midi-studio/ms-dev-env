# HAL Desktop Parity Plan

## Objectif

Atteindre la parité complète entre `hal-teensy` et `hal-desktop` pour que le code métier puisse tourner sur les deux plateformes sans aucune modification.

**Principe fondamental** : Le code métier ne doit JAMAIS savoir sur quelle plateforme il tourne.

---

## Historique

- **Phase 1** : ✅ TERMINÉ - Renommage `hal-sdl` → `hal-desktop` (2025-01-11)
- **Phase 2** : ✅ TERMINÉ - Implémentation `RtMidiTransport` avec libremidi (2025-01-14)
- **Phase 0** : ✅ TERMINÉ - Suppression `clearMouseZones()` (code mort) (2026-01-14)
- **Phase 3** : ✅ TERMINÉ - Renommage `RtMidi` → `LibreMidi` (2026-01-14)
- **Phase 4** : ✅ TERMINÉ - Implémentation `UdpFrameTransport` (2026-01-14)
- **Phase 5** : ✅ TERMINÉ - Alignement API `AppBuilder` (2026-01-14)
- **Phase 7** : ✅ TERMINÉ - Adaptation consommateur `main.cpp` (2026-01-14)

---

## État Actuel - PARITÉ ATTEINTE

### HAL Features

| Feature | hal-teensy | hal-desktop | Status |
|---------|------------|-------------|--------|
| MIDI Transport | `UsbMidi` | `LibreMidiTransport` | ✅ OK |
| Frame Transport | `UsbSerial` (COBS) | `UdpFrameTransport` (raw UDP) | ✅ OK |
| Button Controller | `ButtonController<N>` | `SdlButtonController` | ✅ OK |
| Encoder Controller | `EncoderController<N>` | `SdlEncoderController` | ✅ OK |
| Time Provider | `millis()` | `SDL_GetTicks()` | ✅ OK |
| Log Output | `Serial` | `std::cout` | ✅ OK |
| Storage | `EEPROM/LittleFS` | `MemoryStorage` | ✅ OK |

### AppBuilder API - ALIGNÉE

| Méthode | hal-teensy | hal-desktop | Status |
|---------|------------|-------------|--------|
| Constructeur | `AppBuilder()` | `AppBuilder()` | ✅ Aligné |
| `.midi()` | `UsbMidi` | `NullMidiTransport` | ✅ OK |
| `.midi(config)` | ❌ | `LibreMidiTransport` | ✅ OK |
| `.frames()` | `UsbSerial` | `UdpFrameTransport` | ✅ OK |
| `.frames(config)` | ❌ | `UdpFrameTransport` | ✅ OK |
| `.encoders(defs)` | ✅ | N/A (Teensy only) | N/A |
| `.buttons(defs)` | ✅ | N/A (Teensy only) | N/A |
| `.controllers(input)` | N/A | ✅ | ✅ OK |
| `.inputConfig()` | ✅ | ✅ | ✅ OK |

---

## Décisions d'Architecture (2025-01-14)

### 1. Gestion des Dépendances

**Décision** : hal-desktop reste **header-only**, le consommateur gère les dépendances.

**Rationale** :
- Framework fournit les outils natifs (interfaces, implémentations)
- Consommateur définit et link les dépendances externes (SDL, libremidi, ws2_32, etc.)
- Cohérent avec l'existant (SDL et libremidi déjà gérés ainsi)

**Exemple pour UdpFrameTransport** :
```cpp
// hal-desktop/UdpFrameTransport.hpp - utilise les headers système
#ifdef _WIN32
    #include <winsock2.h>
#else
    #include <sys/socket.h>
    #include <netinet/in.h>
#endif

// Consommateur (midi-studio/CMakeLists.txt) ajoute:
if(WIN32)
    target_link_libraries(... PRIVATE ws2_32)
endif()
```

### 2. SdlBridge et Display

**Décision** : `SdlBridge` reste dans `ui-lvgl`, pas de `SdlDisplayDriver` dans hal-desktop.

**Rationale** :
- Tous les projets utilisent LVGL - pas de cas d'usage "SDL sans LVGL"
- Le driver LVGL SDL (`lv_sdl_window_create`) est bien fait et gère les edge cases
- ROI faible pour une abstraction non nécessaire actuellement
- YAGNI - si besoin futur, on pourra créer `SdlDisplayDriver`

### 3. DesktopRunner

**Décision** : ~~Phase 6 supprimée~~ - Pas de `DesktopRunner` dans le framework.

**Rationale** :
- Créerait une dépendance hal-desktop → ui-lvgl (non souhaité)
- Le boilerplate SDL/LVGL est spécifique au projet (layouts, design, etc.)
- Le consommateur garde le contrôle sur son setup
- `SdlBridge` fait déjà le travail d'encapsulation LVGL+SDL

### 4. `.frames()` pour Desktop

**Décision** : `UdpFrameTransport` implémenté, `.frames()` disponible dans AppBuilder.

**Notes** :
- `.frames()` est **optionnel** - si pas appelé, `hasFrames()` retourne false
- Pas de COBS (oc-bridge mode Virtual utilise RawCodec)
- Chaque datagramme UDP = 1 frame complète

---

## Architecture des Configs

### Différence entre les types de config

| Config | Plateforme | Niveau | Contenu |
|--------|------------|--------|---------|
| `InputConfig` | **Les deux** | Gestes | `longPressMs`, `doubleTapWindowMs`, `latchThresholdMs`, `debounceMs` |
| `ButtonDef[]` | Teensy only | Hardware | `id`, `pin`, `activeLow` |
| `EncoderDef[]` | Teensy only | Hardware | `id`, `pinA`, `pinB`, `ppr`, `rangeAngle`, etc. |
| `InputMapper` | Desktop only | Événements | Keyboard/mouse → Button/Encoder IDs |
| `UdpFrameConfig` | Desktop only | Transport | `host`, `port`, `recvBufferSize` |
| `LibreMidiConfig` | Desktop only | Transport | `appName`, `inputPortPattern`, `outputPortPattern` |

### Pourquoi la différence est légitime

- **Teensy** : Configure des **pins physiques** (hardware)
- **Desktop** : Configure des **événements SDL** (clavier/souris)

Le mapping est différent par nature, mais l'API du code métier (`app.button(ID)`, `app.encoder(ID)`) est identique.

---

## Protocol oc-bridge

### Mode Serial (Teensy physique)
```
Teensy ──Serial USB (COBS)──► oc-bridge ──UDP (raw)──► Bitwig
```

### Mode Virtual (Desktop)
```
Desktop ──UDP:9001 (raw)──► oc-bridge ──UDP:9000 (raw)──► Bitwig
```

**Important** : En mode Virtual, oc-bridge utilise `RawCodec` (pas de COBS).
Chaque datagramme UDP = 1 message complet.

### Ports par défaut (oc-bridge)
- `9000` : UDP host (Bitwig)
- `9001` : UDP virtual controller (Desktop)

Ces ports sont configurables côté oc-bridge ET côté consommateur.

---

## Usage Actuel

### Teensy
```cpp
app = oc::hal::teensy::AppBuilder()
    .midi()
    .frames()
    .encoders(Hardware::ENCODERS)
    .buttons(Hardware::BUTTONS, *mux)
    .inputConfig(Config::Input::CONFIG);
```

### Desktop
```cpp
app = oc::hal::desktop::AppBuilder()
    .midi(midiConfig)
    .frames()  // Optionnel - pour communication avec oc-bridge
    .controllers(input)
    .inputConfig(Config::Input::CONFIG);
```

---

## Fichiers Créés/Modifiés (2026-01-14)

### hal-desktop (open-control)

| Fichier | Action |
|---------|--------|
| `src/.../LibreMidiTransport.hpp` | **CRÉÉ** (remplace RtMidiTransport) |
| `src/.../LibreMidiTransport.cpp` | **CRÉÉ** (remplace RtMidiTransport) |
| `src/.../UdpFrameTransport.hpp` | **CRÉÉ** |
| `src/.../UdpFrameTransport.cpp` | **CRÉÉ** |
| `src/.../AppBuilder.hpp` | **MODIFIÉ** (constructeur sans param, `.controllers(input)`, `.frames()`) |
| `src/.../InputMapper.hpp` | **MODIFIÉ** (suppression `clearMouseZones()`) |
| `test/test_LibreMidiTransport.cpp` | **CRÉÉ** (remplace test_RtMidiTransport) |
| `test/CMakeLists.txt` | **MODIFIÉ** |

### midi-studio/core

| Fichier | Action |
|---------|--------|
| `desktop/main.cpp` | **MODIFIÉ** (`LibreMidiConfig`, nouvelle API AppBuilder) |

### Fichiers Supprimés

| Fichier |
|---------|
| `src/.../RtMidiTransport.hpp` |
| `src/.../RtMidiTransport.cpp` |
| `test/test_RtMidiTransport.cpp` |
| `test/build/` (artefacts) |

---

## Notes Importantes

1. **HwSimulator reste chez le consommateur** : Layout et design sont spécifiques à chaque projet
2. **SdlBridge reste dans ui-lvgl** : C'est un wrapper LVGL-spécifique, bien placé
3. **Pas de COBS sur UDP** : oc-bridge mode Virtual utilise RawCodec
4. **Ports configurables** : Côté oc-bridge ET côté consommateur
5. **`.frames()` optionnel** : Si pas appelé, `hasFrames()` retourne false
6. **Dépendances = responsabilité consommateur** : Framework header-only, consommateur link les libs
7. **Winsock reference counting** : `UdpFrameTransport` gère `WSAStartup`/`WSACleanup` automatiquement
