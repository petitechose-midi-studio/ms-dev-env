# Bridge MIDI Virtual Device - Architecture

> Date: 2025-01-15  
> Status: Plan validé, en attente d'implémentation  
> Implementation Windows: Voir [bridge-midi-wms-helper-plan.md](bridge-midi-wms-helper-plan.md) (RECOMMANDE)  
> Implementation Cross-platform: Voir [bridge-midi-implementation-plan.md](bridge-midi-implementation-plan.md)

## Objectif

Permettre au simulateur WASM (navigateur) de communiquer avec les DAWs via des ports MIDI virtuels, en utilisant Windows MIDI Services (Windows 11+) ou midir (cross-platform).

## Décisions d'architecture

| Aspect | Décision |
|--------|----------|
| Pattern | Trait abstrait + implémentations par plateforme |
| Fallback Windows | midir → loopMIDI (guide utilisateur) |
| Fallback macOS/Linux | midir → ports virtuels natifs |
| Nom port | Configurable (`config.midi.port_name`) |
| Lifecycle | Création au démarrage du bridge |
| Direction | Bidirectionnel (IN + OUT) |
| Message protocole | `MIDI_OUT` / `MIDI_IN` dédiés |
| Format payload | MessagePack structuré |
| Scope MIDI | Tout MIDI 1.0 |
| UI | Aucune pour l'instant |

## Comportement par plateforme

| Plateforme | Backend | Création ports virtuels |
|------------|---------|------------------------|
| Windows + WMS SDK | Windows MIDI Services | Natif via API |
| Windows sans WMS | midir | Manuel → loopMIDI (guide utilisateur) |
| macOS | midir | Natif via CoreMIDI |
| Linux | midir | Natif via ALSA |

## Flow des données

```
Browser (WASM Simulator)
         │
         │ WebSocket
         ▼
┌─────────────────────────┐
│   Bridge virtual_mode   │
│                         │
│  ┌───────────────────┐  │
│  │ Décode protocole  │  │
│  │ OC (COBS)         │  │
│  └─────────┬─────────┘  │
│            │            │
│    ┌───────┴───────┐    │
│    ▼               ▼    │
│  UDP local    MidiPort  │
│  (Bitwig)     (IN+OUT)  │
└─────────────────────────┘
                     │
                     ▼
            ┌───────────────┐
            │ Virtual MIDI  │
            │ Device        │
            └───────┬───────┘
                    │
        ┌───────────┴───────────┐
        ▼                       ▼
    DAW reçoit              DAW envoie
    (Note, CC...)           (Feedback)
```

## Structure des fichiers

```
src/midi/
├── mod.rs                  # Public API: detect(), create_manager()
├── error.rs                # MidiError enum
├── port.rs                 # Traits: MidiPort, MidiInput, MidiOutput
├── message.rs              # MidiMessage enum (MIDI 1.0 complet)
├── codec.rs                # MessagePack <-> bytes MIDI bruts
├── setup.rs                # SetupInstructions (guide loopMIDI)
└── backend/
    ├── mod.rs              # MidiBackend, BackendCapability
    ├── wms.rs              # Windows MIDI Services
    └── midir.rs            # midir (macOS, Linux, loopMIDI)
```

## Traits principaux

```rust
// port.rs

pub trait MidiOutput: Send + Sync {
    fn send(&self, data: &[u8]) -> Result<(), MidiError>;
}

pub trait MidiInput: Send {
    fn receiver(&self) -> &mpsc::Receiver<Vec<u8>>;
}

pub trait MidiPort: Send {
    fn name(&self) -> &str;
    fn output(&self) -> &dyn MidiOutput;
    fn input(&self) -> &dyn MidiInput;
}

pub trait MidiManager: Send {
    fn create_port(&mut self, name: &str) -> Result<Box<dyn MidiPort>, MidiError>;
    fn backend(&self) -> MidiBackend;
}
```

## Messages MIDI (message.rs)

```rust
use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(tag = "type", rename_all = "snake_case")]
pub enum MidiMessage {
    // Channel Voice
    NoteOff { channel: u8, note: u8, velocity: u8 },
    NoteOn { channel: u8, note: u8, velocity: u8 },
    PolyPressure { channel: u8, note: u8, pressure: u8 },
    ControlChange { channel: u8, controller: u8, value: u8 },
    ProgramChange { channel: u8, program: u8 },
    ChannelPressure { channel: u8, pressure: u8 },
    PitchBend { channel: u8, value: u16 },  // 14-bit
    
    // System Common
    SysEx { data: Vec<u8> },
    TimeCode { frame: u8 },
    SongPosition { position: u16 },
    SongSelect { song: u8 },
    TuneRequest,
    
    // System Real-Time
    Clock,
    Start,
    Continue,
    Stop,
    ActiveSensing,
    Reset,
}

impl MidiMessage {
    pub fn to_bytes(&self) -> Vec<u8> { ... }
    pub fn from_bytes(data: &[u8]) -> Result<Self, MidiError> { ... }
}
```

## Détection backend

```rust
pub enum MidiBackend {
    WindowsMidiServices,
    Midir,
}

pub enum BackendCapability {
    /// Peut créer des ports virtuels nativement
    Native { backend: MidiBackend },
    
    /// Ports existants détectés (loopMIDI)
    External { backend: MidiBackend, ports: Vec<String> },
    
    /// Setup requis
    NeedsSetup { instructions: SetupInstructions },
    
    /// MIDI désactivé dans config
    Disabled,
}

pub fn detect(config: &MidiConfig) -> BackendCapability {
    if !config.enabled {
        return BackendCapability::Disabled;
    }
    
    #[cfg(windows)]
    {
        // 1. Essayer WMS
        if wms::is_available() {
            return BackendCapability::Native { 
                backend: MidiBackend::WindowsMidiServices 
            };
        }
        
        // 2. Chercher ports loopMIDI
        if let Some(ports) = midir::find_matching_ports(&config.port_name) {
            return BackendCapability::External { 
                backend: MidiBackend::Midir, 
                ports 
            };
        }
        
        // 3. Guide setup
        BackendCapability::NeedsSetup {
            instructions: setup::windows_loopmidi(&config.port_name)
        }
    }
    
    #[cfg(any(target_os = "macos", target_os = "linux"))]
    {
        BackendCapability::Native { 
            backend: MidiBackend::Midir 
        }
    }
}
```

## Configuration

```toml
# config.toml
[midi]
enabled = true
port_name = "Open Control"
backend = "auto"  # "auto" | "wms" | "midir"
```

```rust
#[derive(Debug, Clone, Deserialize, Serialize, Default)]
pub struct MidiConfig {
    #[serde(default)]
    pub enabled: bool,
    
    #[serde(default = "default_port_name")]
    pub port_name: String,
    
    #[serde(default)]
    pub backend: MidiBackendChoice,
}

#[derive(Debug, Clone, Default, Deserialize, Serialize)]
#[serde(rename_all = "lowercase")]
pub enum MidiBackendChoice {
    #[default]
    Auto,
    Wms,
    Midir,
}
```

## Dépendances Cargo.toml

```toml
[dependencies]
midir = "0.10"
rmp-serde = "1.3"

[target.'cfg(windows)'.dependencies]
windows-core = "0.62"

[target.'cfg(windows)'.build-dependencies]
windows-bindgen = "0.62"
```

## Guide loopMIDI (Windows sans WMS)

Affiché automatiquement si MIDI activé mais aucun backend disponible :

```
Configuration MIDI requise
==========================

1. Télécharger loopMIDI: https://www.tobias-erichsen.de/software/loopmidi.html
2. Installer et lancer loopMIDI
3. Créer un port nommé exactement: "Open Control"
4. Relancer le bridge
```

## Plan d'implémentation

1. **Créer la structure** `src/midi/` avec les fichiers
2. **Implémenter `message.rs`** - Enum MidiMessage + conversion bytes
3. **Implémenter `backend/midir.rs`** - Cross-platform, plus simple
4. **Tester sur macOS/Linux** - Ports virtuels natifs
5. **Implémenter `backend/wms.rs`** - Windows MIDI Services
6. **Tester sur Windows** - Avec le SDK
7. **Ajouter `setup.rs`** - Guide loopMIDI pour fallback Windows
8. **Intégrer dans bridge/runner.rs** - Setup MIDI au démarrage

## Ressources

- Windows MIDI Services SDK: `C:\Program Files\Windows MIDI Services\`
- Doc WMS: https://microsoft.github.io/MIDI/
- midir crate: https://docs.rs/midir
- loopMIDI: https://www.tobias-erichsen.de/software/loopmidi.html
