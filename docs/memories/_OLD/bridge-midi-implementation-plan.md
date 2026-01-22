# Plan d'implémentation MIDI - Étapes détaillées

> Date: 2025-01-15  
> Basé sur: bridge-midi-architecture.md  
> Status: Plan détaillé pour implémentation

## Résumé des découvertes techniques

### APIs disponibles par plateforme

| Plateforme | API | Ports virtuels | Notes |
|------------|-----|----------------|-------|
| macOS | midir + CoreMIDI | `VirtualOutput::create_virtual()` | Natif |
| Linux | midir + ALSA | `VirtualOutput::create_virtual()` | Natif |
| Windows + WMS | Windows MIDI Services | `MidiVirtualDeviceManager::CreateVirtualDevice()` | Requiert SDK |
| Windows sans WMS | midir + WinMM | **Impossible** - connect only | loopMIDI requis |

### Contraintes WMS identifiées

1. **ProductInstanceId** : Max 32 caractères, doit être unique
2. **FunctionBlock** : Au moins 1 requis pour créer un device
3. **Flow** : Session → Config → CreateVirtualDevice → Connection → Open
4. **Bindings** : Générer depuis `.winmd` via `windows-bindgen`
5. **Bootstrapper** : Requis pour desktop apps (`MidiDesktopAppSdkInitializer`)

### Référence: Exemple C++ officiel WMS

Source: https://github.com/microsoft/MIDI/blob/main/samples/cpp-winrt/simple-app-to-app-midi/main_simple_app_to_app.cpp

```cpp
// 1. Init COM + Bootstrapper
winrt::init_apartment();
auto initializer = std::make_shared<init::MidiDesktopAppSdkInitializer>();
initializer->InitializeSdkRuntime();
initializer->EnsureServiceAvailable();

// 2. Session MIDI
auto session = MidiSession::Create(L"Session Name");

// 3. Endpoint Info
MidiDeclaredEndpointInfo endpointInfo;
endpointInfo.Name = L"Open Control";
endpointInfo.ProductInstanceId = L"OPENCTRL00001";
endpointInfo.SupportsMidi10Protocol = true;
endpointInfo.SupportsMidi20Protocol = true;
endpointInfo.HasStaticFunctionBlocks = false;
endpointInfo.SpecificationVersionMajor = 1;
endpointInfo.SpecificationVersionMinor = 1;

// 4. Config + FunctionBlock (minimum 1)
MidiVirtualDeviceCreationConfig config(name, description, manufacturer, endpointInfo);
MidiFunctionBlock block;
block.Number(0);
block.IsActive(true);
block.Name(L"MIDI Port");
block.FirstGroup(MidiGroup(0));
block.GroupCount(1);
block.Direction(MidiFunctionBlockDirection::Bidirectional);
config.FunctionBlocks().Append(block);

// 5. Créer device + connexion
auto virtualDevice = MidiVirtualDeviceManager::CreateVirtualDevice(config);
auto connection = session.CreateEndpointConnection(virtualDevice.DeviceEndpointDeviceId());
connection.AddMessageProcessingPlugin(virtualDevice);
connection.MessageReceived(handler);
connection.Open();  // Port visible aux autres apps après Open()
```

---

## Phase 1: Fondations (2-3h)

### 1.1 Structure des fichiers à créer

```
src/midi/
├── mod.rs              # Exports, re-exports
├── error.rs            # MidiError enum
├── message.rs          # MidiMessage enum (MIDI 1.0)
├── codec.rs            # MessagePack <-> MIDI bytes
└── backend/
    ├── mod.rs          # MidiBackend enum, traits
    ├── midir.rs        # midir backend (Unix + loopMIDI)
    └── wms.rs          # Windows MIDI Services backend
```

### 1.2 Dépendances Cargo.toml

```toml
# Ajouter dans [dependencies]
midir = "0.10"
rmp-serde = "1.3"

# Ajouter dans [target.'cfg(windows)'.dependencies]
# (déjà présent probablement)
windows-core = "0.62"

# Ajouter dans [target.'cfg(windows)'.build-dependencies]
windows-bindgen = "0.62"
```

### 1.3 error.rs - Code exact

```rust
//! MIDI-specific errors

use std::fmt;

/// Errors related to MIDI operations
#[derive(Debug)]
pub enum MidiError {
    /// Failed to initialize MIDI backend
    InitFailed { reason: String },
    
    /// Failed to create virtual port
    CreatePortFailed { name: String, reason: String },
    
    /// Failed to connect to existing port
    ConnectFailed { port: String, reason: String },
    
    /// Port not found
    PortNotFound { name: String },
    
    /// Failed to send MIDI message
    SendFailed { reason: String },
    
    /// Failed to decode MIDI message
    DecodeFailed { reason: String },
    
    /// Backend not available on this platform
    BackendNotAvailable { backend: String },
    
    /// Setup required (loopMIDI on Windows)
    SetupRequired { instructions: String },
}

impl fmt::Display for MidiError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::InitFailed { reason } => write!(f, "MIDI init failed: {}", reason),
            Self::CreatePortFailed { name, reason } => {
                write!(f, "Failed to create port '{}': {}", name, reason)
            }
            Self::ConnectFailed { port, reason } => {
                write!(f, "Failed to connect to '{}': {}", port, reason)
            }
            Self::PortNotFound { name } => write!(f, "Port not found: {}", name),
            Self::SendFailed { reason } => write!(f, "MIDI send failed: {}", reason),
            Self::DecodeFailed { reason } => write!(f, "MIDI decode failed: {}", reason),
            Self::BackendNotAvailable { backend } => {
                write!(f, "Backend '{}' not available", backend)
            }
            Self::SetupRequired { instructions } => write!(f, "{}", instructions),
        }
    }
}

impl std::error::Error for MidiError {}

pub type Result<T> = std::result::Result<T, MidiError>;
```

### 1.4 message.rs - Code exact

```rust
//! MIDI 1.0 message types with MessagePack serialization

use serde::{Deserialize, Serialize};

/// Complete MIDI 1.0 message representation
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(tag = "type", rename_all = "snake_case")]
pub enum MidiMessage {
    // === Channel Voice Messages ===
    NoteOff {
        channel: u8,
        note: u8,
        velocity: u8,
    },
    NoteOn {
        channel: u8,
        note: u8,
        velocity: u8,
    },
    PolyPressure {
        channel: u8,
        note: u8,
        pressure: u8,
    },
    ControlChange {
        channel: u8,
        controller: u8,
        value: u8,
    },
    ProgramChange {
        channel: u8,
        program: u8,
    },
    ChannelPressure {
        channel: u8,
        pressure: u8,
    },
    PitchBend {
        channel: u8,
        /// 14-bit value (0-16383, center = 8192)
        value: u16,
    },

    // === System Common Messages ===
    SysEx {
        /// Raw SysEx data (without F0/F7 framing)
        data: Vec<u8>,
    },
    TimeCodeQuarterFrame {
        message_type: u8,
        value: u8,
    },
    SongPositionPointer {
        /// 14-bit position
        position: u16,
    },
    SongSelect {
        song: u8,
    },
    TuneRequest,

    // === System Real-Time Messages ===
    TimingClock,
    Start,
    Continue,
    Stop,
    ActiveSensing,
    SystemReset,
}

impl MidiMessage {
    /// Convert to raw MIDI bytes
    pub fn to_bytes(&self) -> Vec<u8> {
        match self {
            // Channel Voice
            Self::NoteOff { channel, note, velocity } => {
                vec![0x80 | (channel & 0x0F), note & 0x7F, velocity & 0x7F]
            }
            Self::NoteOn { channel, note, velocity } => {
                vec![0x90 | (channel & 0x0F), note & 0x7F, velocity & 0x7F]
            }
            Self::PolyPressure { channel, note, pressure } => {
                vec![0xA0 | (channel & 0x0F), note & 0x7F, pressure & 0x7F]
            }
            Self::ControlChange { channel, controller, value } => {
                vec![0xB0 | (channel & 0x0F), controller & 0x7F, value & 0x7F]
            }
            Self::ProgramChange { channel, program } => {
                vec![0xC0 | (channel & 0x0F), program & 0x7F]
            }
            Self::ChannelPressure { channel, pressure } => {
                vec![0xD0 | (channel & 0x0F), pressure & 0x7F]
            }
            Self::PitchBend { channel, value } => {
                let lsb = (value & 0x7F) as u8;
                let msb = ((value >> 7) & 0x7F) as u8;
                vec![0xE0 | (channel & 0x0F), lsb, msb]
            }

            // System Common
            Self::SysEx { data } => {
                let mut bytes = vec![0xF0];
                bytes.extend(data.iter().map(|b| b & 0x7F));
                bytes.push(0xF7);
                bytes
            }
            Self::TimeCodeQuarterFrame { message_type, value } => {
                vec![0xF1, ((message_type & 0x07) << 4) | (value & 0x0F)]
            }
            Self::SongPositionPointer { position } => {
                let lsb = (position & 0x7F) as u8;
                let msb = ((position >> 7) & 0x7F) as u8;
                vec![0xF2, lsb, msb]
            }
            Self::SongSelect { song } => vec![0xF3, song & 0x7F],
            Self::TuneRequest => vec![0xF6],

            // System Real-Time
            Self::TimingClock => vec![0xF8],
            Self::Start => vec![0xFA],
            Self::Continue => vec![0xFB],
            Self::Stop => vec![0xFC],
            Self::ActiveSensing => vec![0xFE],
            Self::SystemReset => vec![0xFF],
        }
    }

    /// Parse from raw MIDI bytes
    pub fn from_bytes(data: &[u8]) -> Option<Self> {
        if data.is_empty() {
            return None;
        }

        let status = data[0];
        let channel = status & 0x0F;

        match status & 0xF0 {
            0x80 if data.len() >= 3 => Some(Self::NoteOff {
                channel,
                note: data[1],
                velocity: data[2],
            }),
            0x90 if data.len() >= 3 => {
                // Note On with velocity 0 = Note Off
                if data[2] == 0 {
                    Some(Self::NoteOff {
                        channel,
                        note: data[1],
                        velocity: 0,
                    })
                } else {
                    Some(Self::NoteOn {
                        channel,
                        note: data[1],
                        velocity: data[2],
                    })
                }
            }
            0xA0 if data.len() >= 3 => Some(Self::PolyPressure {
                channel,
                note: data[1],
                pressure: data[2],
            }),
            0xB0 if data.len() >= 3 => Some(Self::ControlChange {
                channel,
                controller: data[1],
                value: data[2],
            }),
            0xC0 if data.len() >= 2 => Some(Self::ProgramChange {
                channel,
                program: data[1],
            }),
            0xD0 if data.len() >= 2 => Some(Self::ChannelPressure {
                channel,
                pressure: data[1],
            }),
            0xE0 if data.len() >= 3 => Some(Self::PitchBend {
                channel,
                value: (data[1] as u16) | ((data[2] as u16) << 7),
            }),
            0xF0 => match status {
                0xF0 => {
                    // SysEx - find end
                    let end = data.iter().position(|&b| b == 0xF7).unwrap_or(data.len());
                    Some(Self::SysEx {
                        data: data[1..end].to_vec(),
                    })
                }
                0xF1 if data.len() >= 2 => Some(Self::TimeCodeQuarterFrame {
                    message_type: (data[1] >> 4) & 0x07,
                    value: data[1] & 0x0F,
                }),
                0xF2 if data.len() >= 3 => Some(Self::SongPositionPointer {
                    position: (data[1] as u16) | ((data[2] as u16) << 7),
                }),
                0xF3 if data.len() >= 2 => Some(Self::SongSelect { song: data[1] }),
                0xF6 => Some(Self::TuneRequest),
                0xF8 => Some(Self::TimingClock),
                0xFA => Some(Self::Start),
                0xFB => Some(Self::Continue),
                0xFC => Some(Self::Stop),
                0xFE => Some(Self::ActiveSensing),
                0xFF => Some(Self::SystemReset),
                _ => None,
            },
            _ => None,
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_note_on_roundtrip() {
        let msg = MidiMessage::NoteOn {
            channel: 0,
            note: 60,
            velocity: 100,
        };
        let bytes = msg.to_bytes();
        assert_eq!(bytes, vec![0x90, 60, 100]);
        assert_eq!(MidiMessage::from_bytes(&bytes), Some(msg));
    }

    #[test]
    fn test_pitch_bend_roundtrip() {
        let msg = MidiMessage::PitchBend {
            channel: 5,
            value: 8192, // Center
        };
        let bytes = msg.to_bytes();
        assert_eq!(MidiMessage::from_bytes(&bytes), Some(msg));
    }
}
```

### 1.5 codec.rs - Code exact

```rust
//! MessagePack codec for MIDI messages

use crate::midi::error::{MidiError, Result};
use crate::midi::message::MidiMessage;

/// Encode a MIDI message to MessagePack bytes
pub fn encode(msg: &MidiMessage) -> Vec<u8> {
    rmp_serde::to_vec(msg).expect("MidiMessage serialization cannot fail")
}

/// Decode a MIDI message from MessagePack bytes
pub fn decode(data: &[u8]) -> Result<MidiMessage> {
    rmp_serde::from_slice(data).map_err(|e| MidiError::DecodeFailed {
        reason: e.to_string(),
    })
}

/// Encode a MIDI message to raw MIDI bytes (for sending to port)
pub fn to_midi_bytes(msg: &MidiMessage) -> Vec<u8> {
    msg.to_bytes()
}

/// Decode raw MIDI bytes to a MIDI message
pub fn from_midi_bytes(data: &[u8]) -> Result<MidiMessage> {
    MidiMessage::from_bytes(data).ok_or_else(|| MidiError::DecodeFailed {
        reason: format!("Invalid MIDI data: {:02X?}", data),
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_msgpack_roundtrip() {
        let msg = MidiMessage::ControlChange {
            channel: 0,
            controller: 1,
            value: 64,
        };
        let encoded = encode(&msg);
        let decoded = decode(&encoded).unwrap();
        assert_eq!(msg, decoded);
    }
}
```

### 1.6 mod.rs - Code exact

```rust
//! MIDI virtual device support
//!
//! Provides cross-platform MIDI virtual port creation:
//! - macOS/Linux: Native virtual ports via midir
//! - Windows + WMS: Virtual device via Windows MIDI Services
//! - Windows sans WMS: Connect to loopMIDI ports

pub mod backend;
pub mod codec;
pub mod error;
pub mod message;

pub use backend::{detect_backend, BackendCapability, MidiBackend};
pub use error::{MidiError, Result};
pub use message::MidiMessage;
```

---

## Phase 2: Backend midir (3-4h)

### 2.1 backend/mod.rs - Code exact

```rust
//! MIDI backend abstraction

pub mod midir;

#[cfg(all(windows, feature = "wms"))]
pub mod wms;

use crate::midi::error::{MidiError, Result};
use std::sync::mpsc;

/// Available MIDI backends
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum MidiBackend {
    /// midir - cross-platform (virtual ports on Unix, connect-only on Windows)
    Midir,
    /// Windows MIDI Services (Windows 11+)
    #[cfg(windows)]
    WindowsMidiServices,
}

/// Result of backend detection
#[derive(Debug)]
pub enum BackendCapability {
    /// Can create virtual ports natively
    Native { backend: MidiBackend },
    /// Can connect to existing ports only (loopMIDI)
    ConnectOnly {
        backend: MidiBackend,
        available_ports: Vec<String>,
    },
    /// No backend available, setup required
    NeedsSetup { instructions: String },
    /// MIDI disabled in config
    Disabled,
}

/// Trait for MIDI output port
pub trait MidiOutput: Send {
    fn send(&self, data: &[u8]) -> Result<()>;
    fn name(&self) -> &str;
}

/// Trait for MIDI input port  
pub trait MidiInput: Send {
    fn receiver(&self) -> &mpsc::Receiver<Vec<u8>>;
    fn name(&self) -> &str;
}

/// Bidirectional MIDI port
pub struct MidiPort {
    pub name: String,
    pub output: Box<dyn MidiOutput>,
    pub input: Box<dyn MidiInput>,
}

/// Detect the best available backend for the current platform
pub fn detect_backend(enabled: bool, port_name: &str) -> BackendCapability {
    if !enabled {
        return BackendCapability::Disabled;
    }

    #[cfg(unix)]
    {
        // macOS/Linux: midir can create virtual ports
        BackendCapability::Native {
            backend: MidiBackend::Midir,
        }
    }

    #[cfg(windows)]
    {
        // Windows: try WMS first, then loopMIDI
        #[cfg(feature = "wms")]
        if wms::is_available() {
            return BackendCapability::Native {
                backend: MidiBackend::WindowsMidiServices,
            };
        }

        // Check for loopMIDI ports
        match midir::find_ports_matching(port_name) {
            Ok(ports) if !ports.is_empty() => BackendCapability::ConnectOnly {
                backend: MidiBackend::Midir,
                available_ports: ports,
            },
            _ => BackendCapability::NeedsSetup {
                instructions: setup_instructions_windows(port_name),
            },
        }
    }
}

#[cfg(windows)]
fn setup_instructions_windows(port_name: &str) -> String {
    format!(
        r#"
MIDI Setup Required
===================

Windows MIDI Services is not available. Please install loopMIDI:

1. Download loopMIDI from:
   https://www.tobias-erichsen.de/software/loopmidi.html

2. Install and launch loopMIDI

3. Create a port named exactly: "{}"

4. Restart the bridge

The bridge will automatically connect to this port.
"#,
        port_name
    )
}
```

### 2.2 backend/midir.rs - Code exact

```rust
//! midir backend implementation
//!
//! - Unix: Creates virtual ports via VirtualOutput/VirtualInput traits
//! - Windows: Connects to existing ports (loopMIDI)

use crate::midi::backend::{MidiInput, MidiOutput, MidiPort};
use crate::midi::error::{MidiError, Result};
use ::midir::{MidiInput as MidirInput, MidiOutput as MidirOutput, MidiOutputConnection};
use std::sync::mpsc::{self, Receiver, Sender};
use std::sync::{Arc, Mutex};

#[cfg(unix)]
use ::midir::os::unix::{VirtualInput, VirtualOutput};

/// midir-based MIDI output
pub struct MidirOutputPort {
    name: String,
    connection: Arc<Mutex<MidiOutputConnection>>,
}

impl MidiOutput for MidirOutputPort {
    fn send(&self, data: &[u8]) -> Result<()> {
        self.connection
            .lock()
            .map_err(|_| MidiError::SendFailed {
                reason: "Lock poisoned".into(),
            })?
            .send(data)
            .map_err(|e| MidiError::SendFailed {
                reason: e.to_string(),
            })
    }

    fn name(&self) -> &str {
        &self.name
    }
}

/// midir-based MIDI input
pub struct MidirInputPort {
    name: String,
    rx: Receiver<Vec<u8>>,
    // Keep connection alive
    _connection: ::midir::MidiInputConnection<()>,
}

impl MidiInput for MidirInputPort {
    fn receiver(&self) -> &Receiver<Vec<u8>> {
        &self.rx
    }

    fn name(&self) -> &str {
        &self.name
    }
}

/// Create a virtual MIDI port (Unix only)
#[cfg(unix)]
pub fn create_virtual_port(name: &str) -> Result<MidiPort> {
    let output_name = format!("{} Out", name);
    let input_name = format!("{} In", name);

    // Create virtual output
    let midi_out = MidirOutput::new("open-control").map_err(|e| MidiError::InitFailed {
        reason: e.to_string(),
    })?;

    let out_conn = midi_out
        .create_virtual(&output_name)
        .map_err(|e| MidiError::CreatePortFailed {
            name: output_name.clone(),
            reason: e.to_string(),
        })?;

    // Create virtual input with callback
    let midi_in = MidirInput::new("open-control").map_err(|e| MidiError::InitFailed {
        reason: e.to_string(),
    })?;

    let (tx, rx): (Sender<Vec<u8>>, Receiver<Vec<u8>>) = mpsc::channel();

    let in_conn = midi_in
        .create_virtual(
            &input_name,
            move |_timestamp, message, _| {
                let _ = tx.send(message.to_vec());
            },
            (),
        )
        .map_err(|e| MidiError::CreatePortFailed {
            name: input_name.clone(),
            reason: e.to_string(),
        })?;

    Ok(MidiPort {
        name: name.to_string(),
        output: Box::new(MidirOutputPort {
            name: output_name,
            connection: Arc::new(Mutex::new(out_conn)),
        }),
        input: Box::new(MidirInputPort {
            name: input_name,
            rx,
            _connection: in_conn,
        }),
    })
}

/// Connect to existing MIDI ports (Windows - loopMIDI)
#[cfg(windows)]
pub fn connect_to_port(port_name: &str) -> Result<MidiPort> {
    // Find output port
    let midi_out = MidirOutput::new("open-control").map_err(|e| MidiError::InitFailed {
        reason: e.to_string(),
    })?;

    let out_ports = midi_out.ports();
    let out_port = out_ports
        .iter()
        .find(|p| {
            midi_out
                .port_name(p)
                .map(|n| n.contains(port_name))
                .unwrap_or(false)
        })
        .ok_or_else(|| MidiError::PortNotFound {
            name: format!("{} (output)", port_name),
        })?;

    let out_conn = midi_out
        .connect(out_port, "open-control-out")
        .map_err(|e| MidiError::ConnectFailed {
            port: port_name.to_string(),
            reason: e.to_string(),
        })?;

    // Find input port
    let midi_in = MidirInput::new("open-control").map_err(|e| MidiError::InitFailed {
        reason: e.to_string(),
    })?;

    let in_ports = midi_in.ports();
    let in_port = in_ports
        .iter()
        .find(|p| {
            midi_in
                .port_name(p)
                .map(|n| n.contains(port_name))
                .unwrap_or(false)
        })
        .ok_or_else(|| MidiError::PortNotFound {
            name: format!("{} (input)", port_name),
        })?;

    let (tx, rx): (Sender<Vec<u8>>, Receiver<Vec<u8>>) = mpsc::channel();

    let in_conn = midi_in
        .connect(
            in_port,
            "open-control-in",
            move |_timestamp, message, _| {
                let _ = tx.send(message.to_vec());
            },
            (),
        )
        .map_err(|e| MidiError::ConnectFailed {
            port: port_name.to_string(),
            reason: e.to_string(),
        })?;

    Ok(MidiPort {
        name: port_name.to_string(),
        output: Box::new(MidirOutputPort {
            name: port_name.to_string(),
            connection: Arc::new(Mutex::new(out_conn)),
        }),
        input: Box::new(MidirInputPort {
            name: port_name.to_string(),
            rx,
            _connection: in_conn,
        }),
    })
}

/// Find ports matching a name pattern
pub fn find_ports_matching(pattern: &str) -> Result<Vec<String>> {
    let midi_out = MidirOutput::new("open-control-scan").map_err(|e| MidiError::InitFailed {
        reason: e.to_string(),
    })?;

    let ports: Vec<String> = midi_out
        .ports()
        .iter()
        .filter_map(|p| midi_out.port_name(p).ok())
        .filter(|name| name.contains(pattern))
        .collect();

    Ok(ports)
}

/// List all available MIDI ports
pub fn list_all_ports() -> Result<(Vec<String>, Vec<String>)> {
    let midi_out = MidirOutput::new("open-control-scan").map_err(|e| MidiError::InitFailed {
        reason: e.to_string(),
    })?;
    let midi_in = MidirInput::new("open-control-scan").map_err(|e| MidiError::InitFailed {
        reason: e.to_string(),
    })?;

    let outputs: Vec<String> = midi_out
        .ports()
        .iter()
        .filter_map(|p| midi_out.port_name(p).ok())
        .collect();

    let inputs: Vec<String> = midi_in
        .ports()
        .iter()
        .filter_map(|p| midi_in.port_name(p).ok())
        .collect();

    Ok((inputs, outputs))
}
```

---

## Phase 3: Backend WMS (4-5h)

### 3.1 build.rs - Code exact

```rust
//! Build script for Windows MIDI Services bindings generation

fn main() {
    #[cfg(windows)]
    {
        generate_wms_bindings();
    }
}

#[cfg(windows)]
fn generate_wms_bindings() {
    use std::path::PathBuf;

    // Check for WMS SDK
    let sdk_paths = [
        PathBuf::from(r"C:\Program Files\Windows MIDI Services"),
        PathBuf::from(r"C:\Program Files (x86)\Windows MIDI Services"),
    ];

    let sdk_path = sdk_paths.iter().find(|p| p.exists());

    let Some(sdk_path) = sdk_path else {
        println!("cargo:warning=Windows MIDI Services SDK not found");
        println!("cargo:warning=WMS backend will not be available");
        println!("cargo:warning=Install from: https://microsoft.github.io/MIDI/");
        return;
    };

    // Find .winmd file
    let winmd_path = sdk_path.join("Microsoft.Windows.Devices.Midi2.winmd");
    if !winmd_path.exists() {
        println!("cargo:warning=WMS .winmd file not found at {:?}", winmd_path);
        return;
    }

    println!("cargo:rerun-if-changed={}", winmd_path.display());
    println!("cargo:rustc-cfg=feature=\"wms\"");

    // Generate bindings
    let out_dir = std::env::var("OUT_DIR").unwrap();
    let out_path = PathBuf::from(&out_dir).join("wms_bindings.rs");

    let result = std::process::Command::new("windows-bindgen")
        .args([
            "--in",
            &winmd_path.to_string_lossy(),
            "--out",
            &out_path.to_string_lossy(),
            "--filter",
            "Microsoft.Windows.Devices.Midi2",
        ])
        .status();

    match result {
        Ok(status) if status.success() => {
            println!("cargo:warning=WMS bindings generated successfully");
        }
        Ok(status) => {
            println!(
                "cargo:warning=windows-bindgen failed with status: {}",
                status
            );
        }
        Err(e) => {
            println!("cargo:warning=Failed to run windows-bindgen: {}", e);
            println!("cargo:warning=Install with: cargo install windows-bindgen");
        }
    }
}
```

### 3.2 backend/wms.rs - Code Rust complet

```rust
//! Windows MIDI Services backend
//!
//! Creates native virtual MIDI devices on Windows 11+
//! Based on: https://github.com/microsoft/MIDI/blob/main/samples/cpp-winrt/simple-app-to-app-midi/

#![cfg(all(windows, feature = "wms"))]

use crate::midi::backend::{MidiInput, MidiOutput, MidiPort};
use crate::midi::error::{MidiError, Result};
use std::sync::mpsc::{self, Receiver, Sender};
use std::sync::{Arc, Mutex};

// Include generated bindings
include!(concat!(env!("OUT_DIR"), "/wms_bindings.rs"));

use Microsoft::Windows::Devices::Midi2::*;
use Microsoft::Windows::Devices::Midi2::Endpoints::Virtual::*;

/// WMS Virtual Device wrapper
pub struct WmsVirtualDevice {
    name: String,
    session: MidiSession,
    device: MidiVirtualDevice,
    connection: MidiEndpointConnection,
    rx: Receiver<Vec<u8>>,
}

/// Check if WMS is available on this system
pub fn is_available() -> bool {
    // Check if the virtual device transport is available
    match MidiVirtualDeviceManager::IsTransportAvailable() {
        Ok(available) => available,
        Err(_) => false,
    }
}

/// Create a virtual MIDI device via WMS
pub fn create_virtual_device(name: &str, product_id: &str) -> Result<MidiPort> {
    if !is_available() {
        return Err(MidiError::BackendNotAvailable {
            backend: "Windows MIDI Services".into(),
        });
    }

    // 1. Create MIDI Session
    let session = MidiSession::Create(&name.into())
        .map_err(|e| MidiError::InitFailed { reason: e.to_string() })?;

    // 2. Create endpoint info
    let mut endpoint_info = MidiDeclaredEndpointInfo::default();
    endpoint_info.Name = name.into();
    endpoint_info.ProductInstanceId = product_id.into();
    endpoint_info.SupportsMidi10Protocol = true;
    endpoint_info.SupportsMidi20Protocol = false;  // MIDI 1.0 suffit
    endpoint_info.HasStaticFunctionBlocks = true;
    endpoint_info.DeclaredFunctionBlockCount = 1;
    endpoint_info.SpecificationVersionMajor = 1;
    endpoint_info.SpecificationVersionMinor = 1;

    // 3. Create config
    let config = MidiVirtualDeviceCreationConfig::CreateInstance(
        &name.into(),
        &"Open Control Bridge virtual MIDI device".into(),
        &"Open Control".into(),
        &endpoint_info,
    ).map_err(|e| MidiError::CreatePortFailed { 
        name: name.into(), 
        reason: e.to_string() 
    })?;

    // 4. Add function block (required, at least 1)
    let mut block = MidiFunctionBlock::default();
    block.Number = 0;
    block.IsActive = true;
    block.Name = "MIDI Port".into();
    block.FirstGroupIndex = 0;
    block.GroupCount = 1;
    block.Direction = MidiFunctionBlockDirection::Bidirectional;
    block.RepresentsMidi10Connection = MidiFunctionBlockRepresentsMidi10Connection::YesBandwidthUnrestricted;
    
    config.FunctionBlocks()
        .map_err(|e| MidiError::CreatePortFailed { name: name.into(), reason: e.to_string() })?
        .Append(&block)
        .map_err(|e| MidiError::CreatePortFailed { name: name.into(), reason: e.to_string() })?;

    // 5. Create virtual device
    let device = MidiVirtualDeviceManager::CreateVirtualDevice(&config)
        .map_err(|e| MidiError::CreatePortFailed { 
            name: name.into(), 
            reason: e.to_string() 
        })?;

    // 6. Create connection to device endpoint
    let endpoint_id = device.DeviceEndpointDeviceId()
        .map_err(|e| MidiError::CreatePortFailed { name: name.into(), reason: e.to_string() })?;
    
    let connection = session.CreateEndpointConnection(&endpoint_id)
        .map_err(|e| MidiError::ConnectFailed { 
            port: name.into(), 
            reason: e.to_string() 
        })?;

    // 7. Add device as message processing plugin
    connection.AddMessageProcessingPlugin(&device)
        .map_err(|e| MidiError::ConnectFailed { port: name.into(), reason: e.to_string() })?;

    // 8. Setup message received handler
    let (tx, rx): (Sender<Vec<u8>>, Receiver<Vec<u8>>) = mpsc::channel();
    
    connection.MessageReceived(&TypedEventHandler::new(move |_, args: &Option<MidiMessageReceivedEventArgs>| {
        if let Some(args) = args {
            if let Ok(packet) = args.GetMessagePacket() {
                // Convert UMP to MIDI 1.0 bytes
                // TODO: Implement proper UMP to MIDI 1.0 conversion
                let _ = tx.send(vec![]);  // Placeholder
            }
        }
        Ok(())
    })).map_err(|e| MidiError::ConnectFailed { port: name.into(), reason: e.to_string() })?;

    // 9. Open connection (port becomes visible to other apps)
    connection.Open()
        .map_err(|e| MidiError::ConnectFailed { port: name.into(), reason: e.to_string() })?;

    // Create port wrapper
    let wms_device = WmsVirtualDevice {
        name: name.to_string(),
        session,
        device,
        connection,
        rx,
    };

    Ok(MidiPort {
        name: name.to_string(),
        output: Box::new(WmsOutput { 
            connection: wms_device.connection.clone(),
            name: name.to_string(),
        }),
        input: Box::new(WmsInput {
            name: name.to_string(),
            rx: wms_device.rx,
        }),
    })
}

struct WmsOutput {
    connection: MidiEndpointConnection,
    name: String,
}

impl MidiOutput for WmsOutput {
    fn send(&self, data: &[u8]) -> Result<()> {
        // Convert MIDI 1.0 bytes to UMP and send
        // TODO: Implement proper MIDI 1.0 to UMP conversion
        let timestamp = MidiClock::Now().unwrap_or(0);
        
        // For MIDI 1.0 channel voice messages, use MidiMessage32
        if !data.is_empty() {
            let word = match data.len() {
                1 => (data[0] as u32) << 16,
                2 => ((data[0] as u32) << 16) | ((data[1] as u32) << 8),
                3 => ((data[0] as u32) << 16) | ((data[1] as u32) << 8) | (data[2] as u32),
                _ => return Ok(()), // SysEx needs different handling
            };
            
            // Type 2 = MIDI 1.0 Channel Voice Message
            let ump_word = 0x20000000 | word;
            
            self.connection.SendSingleMessageWords(timestamp, ump_word)
                .map_err(|e| MidiError::SendFailed { reason: e.to_string() })?;
        }
        Ok(())
    }

    fn name(&self) -> &str {
        &self.name
    }
}

struct WmsInput {
    name: String,
    rx: Receiver<Vec<u8>>,
}

impl MidiInput for WmsInput {
    fn receiver(&self) -> &Receiver<Vec<u8>> {
        &self.rx
    }

    fn name(&self) -> &str {
        &self.name
    }
}
```

**Note**: Ce code est une ébauche. Les points à finaliser après génération des bindings :
- Vérifier les noms exacts des types générés
- Implémenter la conversion UMP ↔ MIDI 1.0 correctement
- Gérer le cleanup (Drop trait) pour fermer proprement la session

---

## Phase 4: Configuration (1-2h)

### 4.1 Ajouter à config.rs

```rust
// Ajouter au début du fichier, avec les autres imports
use crate::midi;

// Ajouter dans la struct Config
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(default)]
pub struct Config {
    pub bridge: BridgeConfig,
    pub logs: LogsConfig,
    pub ui: UiConfig,
    pub midi: MidiConfig,  // NOUVEAU
}

// Nouvelle struct MidiConfig
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(default)]
pub struct MidiConfig {
    /// Enable MIDI virtual device
    pub enabled: bool,
    /// Name of the virtual MIDI port
    pub port_name: String,
    /// Preferred backend: "auto", "wms", "midir"
    pub backend: MidiBackendChoice,
}

#[derive(Debug, Clone, Default, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "lowercase")]
pub enum MidiBackendChoice {
    #[default]
    Auto,
    Wms,
    Midir,
}

impl Default for MidiConfig {
    fn default() -> Self {
        Self {
            enabled: false,
            port_name: "Open Control".to_string(),
            backend: MidiBackendChoice::Auto,
        }
    }
}

// Ajouter dans impl Default for Config
impl Default for Config {
    fn default() -> Self {
        Self {
            bridge: BridgeConfig::default(),
            logs: LogsConfig::default(),
            ui: UiConfig::default(),
            midi: MidiConfig::default(),  // NOUVEAU
        }
    }
}
```

### 4.2 config/default.toml - Ajouter section

```toml
# ... existing config ...

[midi]
enabled = false
port_name = "Open Control"
backend = "auto"
```

---

## Phase 5: Intégration bridge (2-3h)

### 5.1 main.rs - Ajouter module

```rust
// Ajouter après les autres mod declarations
mod midi;
```

### 5.2 bridge/runner.rs - Intégration

```rust
// Au début du fichier, ajouter
use crate::midi::{self, BackendCapability, MidiMessage};

// Nouvelle fonction pour setup MIDI
fn setup_midi(config: &crate::config::Config) -> Option<midi::backend::MidiPort> {
    let capability = midi::detect_backend(config.midi.enabled, &config.midi.port_name);

    match capability {
        BackendCapability::Disabled => {
            tracing::debug!("MIDI disabled in config");
            None
        }
        BackendCapability::Native { backend } => {
            tracing::info!("MIDI backend: {:?} (native virtual ports)", backend);
            
            #[cfg(unix)]
            {
                midi::backend::midir::create_virtual_port(&config.midi.port_name).ok()
            }
            #[cfg(windows)]
            {
                #[cfg(feature = "wms")]
                {
                    midi::backend::wms::create_virtual_device(
                        &config.midi.port_name,
                        "OPENCTRL001",
                    ).ok()
                }
                #[cfg(not(feature = "wms"))]
                {
                    None
                }
            }
        }
        BackendCapability::ConnectOnly { backend, available_ports } => {
            tracing::info!(
                "MIDI backend: {:?} (connecting to existing port)",
                backend
            );
            tracing::debug!("Available ports: {:?}", available_ports);
            
            #[cfg(windows)]
            {
                midi::backend::midir::connect_to_port(&config.midi.port_name).ok()
            }
            #[cfg(not(windows))]
            {
                None
            }
        }
        BackendCapability::NeedsSetup { instructions } => {
            tracing::warn!("{}", instructions);
            None
        }
    }
}

// Dans serial_mode() ou virtual_mode(), après création des transports:
pub(super) async fn serial_mode(
    config: &BridgeConfig,
    full_config: &crate::config::Config,  // Ajouter ce paramètre
    // ... autres params
) -> Result<()> {
    // ... existing code ...

    // Setup MIDI (nouveau)
    let midi_port = setup_midi(full_config);
    if let Some(ref port) = midi_port {
        tracing::info!("MIDI port created: {}", port.name);
    }

    // ... rest of function, pass midi_port to session if needed
}
```

---

## Phase 6: Tests (1-2h)

### 6.1 Tests à effectuer

| Test | Commande | Résultat attendu |
|------|----------|------------------|
| Build macOS/Linux | `cargo build` | Compile sans erreur |
| Build Windows | `cargo build` | Compile (warning si WMS absent) |
| Unit tests | `cargo test` | Tous les tests passent |
| Port virtuel Unix | Lancer bridge + vérifier dans DAW | Port visible |
| Port loopMIDI Windows | Créer port loopMIDI + lancer bridge | Connexion réussie |
| WMS Windows 11 | Installer SDK + lancer bridge | Port virtuel créé |

### 6.2 Tests unitaires à ajouter

```rust
// tests/midi_tests.rs

#[test]
fn test_midi_message_to_bytes() {
    let msg = crate::midi::MidiMessage::NoteOn {
        channel: 0,
        note: 60,
        velocity: 100,
    };
    assert_eq!(msg.to_bytes(), vec![0x90, 60, 100]);
}

#[test]
fn test_midi_message_msgpack_roundtrip() {
    let msg = crate::midi::MidiMessage::ControlChange {
        channel: 5,
        controller: 1,
        value: 127,
    };
    let encoded = crate::midi::codec::encode(&msg);
    let decoded = crate::midi::codec::decode(&encoded).unwrap();
    assert_eq!(msg, decoded);
}
```

---

## Ordre d'exécution recommandé

```
Jour 1 (Fondations):
├── 1.1 Créer structure fichiers
├── 1.2 Ajouter dépendances Cargo.toml
├── 1.3 Implémenter error.rs
├── 1.4 Implémenter message.rs
├── 1.5 Implémenter codec.rs
└── 1.6 Implémenter mod.rs

Jour 2 (Backend midir):
├── 2.1 backend/mod.rs
├── 2.2 backend/midir.rs (Unix)
├── 2.3 Tester sur macOS/Linux
└── 2.4 backend/midir.rs (Windows connect)

Jour 3 (Config + Integration):
├── 4.1 MidiConfig dans config.rs
├── 5.1 mod midi dans main.rs
├── 5.2 setup_midi() dans runner.rs
└── Tests d'intégration

Jour 4 (WMS - optionnel):
├── 3.1 build.rs
├── 3.2 backend/wms.rs
└── Tests Windows 11
```

---

## Fichiers à modifier (récapitulatif)

| Fichier | Action |
|---------|--------|
| `Cargo.toml` | Ajouter midir, rmp-serde |
| `src/main.rs` | Ajouter `mod midi;` |
| `src/config.rs` | Ajouter MidiConfig |
| `config/default.toml` | Ajouter section [midi] |
| `src/bridge/runner.rs` | Ajouter setup_midi() |
| `build.rs` | Créer (pour WMS) |

## Fichiers à créer

| Fichier | Contenu |
|---------|---------|
| `src/midi/mod.rs` | Exports |
| `src/midi/error.rs` | MidiError enum |
| `src/midi/message.rs` | MidiMessage enum |
| `src/midi/codec.rs` | MessagePack codec |
| `src/midi/backend/mod.rs` | Backend traits |
| `src/midi/backend/midir.rs` | midir impl |
| `src/midi/backend/wms.rs` | WMS impl (optionnel) |
