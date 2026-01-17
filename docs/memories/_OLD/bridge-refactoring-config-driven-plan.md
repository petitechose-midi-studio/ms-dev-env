# Plan de Refactoring: Architecture Config-Driven

## Objectif
Rendre le code 100% agnostique (zéro référence à un device/plateforme spécifique).
Toute configuration spécifique est externalisée dans des fichiers TOML.

---

## PHASE 1: Structures de Configuration

### Fichier: `src/config.rs`

**Ajouter les nouvelles structures:**

```rust
/// Configuration de détection de device USB
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DeviceConfig {
    /// Nom affiché du device
    pub name: String,
    /// USB Vendor ID
    pub vid: u16,
    /// Liste des USB Product IDs acceptés
    pub pid_list: Vec<u16>,
    /// Hints de nom par plateforme (optionnel)
    #[serde(default)]
    pub name_hint: PlatformNameHint,
}

/// Hints de nom de port par plateforme
#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct PlatformNameHint {
    pub windows: Option<String>,
    pub macos: Option<String>,
    pub linux: Option<String>,
}

impl PlatformNameHint {
    /// Retourne le hint pour la plateforme courante
    pub fn current(&self) -> Option<&str> {
        #[cfg(windows)]
        { self.windows.as_deref() }
        #[cfg(target_os = "macos")]
        { self.macos.as_deref() }
        #[cfg(target_os = "linux")]
        { self.linux.as_deref() }
        #[cfg(not(any(windows, target_os = "macos", target_os = "linux")))]
        { None }
    }
}
```

**Modifier `BridgeConfig`:**

Supprimer le commentaire "empty = auto-detect Teensy" (ligne 41).

Ajouter un champ:
```rust
/// Preset de device sélectionné (nom du fichier sans .toml)
/// None = pas de détection automatique
pub device_preset: Option<String>,
```

---

## PHASE 2: Chargement des Presets

### Fichier: `src/config.rs`

**Ajouter fonctions de chargement:**

```rust
/// Chemin vers le dossier devices
fn devices_dir() -> Result<PathBuf> {
    let exe = std::env::current_exe()?;
    let dir = exe.parent().ok_or(...)?;
    Ok(dir.join("config").join("devices"))
}

/// Liste les presets disponibles (noms sans extension)
pub fn list_device_presets() -> Vec<String> {
    let dir = match devices_dir() {
        Ok(d) => d,
        Err(_) => return vec![],
    };
    
    std::fs::read_dir(dir)
        .into_iter()
        .flatten()
        .filter_map(|e| e.ok())
        .filter(|e| e.path().extension().map(|x| x == "toml").unwrap_or(false))
        .filter_map(|e| e.path().file_stem()?.to_str().map(String::from))
        .collect()
}

/// Charge un preset de device par nom
pub fn load_device_preset(name: &str) -> Result<DeviceConfig> {
    let dir = devices_dir()?;
    let path = dir.join(format!("{}.toml", name));
    let content = std::fs::read_to_string(&path)?;
    let wrapper: DevicePresetFile = toml::from_str(&content)?;
    Ok(wrapper.device)
}

#[derive(Deserialize)]
struct DevicePresetFile {
    device: DeviceConfig,
}
```

---

## PHASE 3: Détection Générique

### Fichier: `src/transport/serial.rs`

**Supprimer:**
- Ligne 16: `use crate::serial;`

**Ajouter imports:**
```rust
use crate::config::DeviceConfig;
use serialport::{SerialPortInfo, SerialPortType};
```

**Ajouter dans `impl SerialTransport`:**

```rust
/// Détecte un device USB selon la configuration
pub fn detect(config: &DeviceConfig) -> Result<String> {
    let ports = serialport::available_ports().unwrap_or_default();
    
    let matching: Vec<_> = ports.iter()
        .filter(|p| matches_device(p, config))
        .collect();
    
    match matching.len() {
        0 => Err(BridgeError::NoDeviceFound),
        1 => Ok(matching[0].port_name.clone()),
        n => Err(BridgeError::MultipleDevicesFound { count: n }),
    }
}

/// Ouvre un port série (USB CDC - baud rate ignoré)
pub fn open(port_name: &str) -> Result<Box<dyn serialport::SerialPort>> {
    // Code actuel de serial::open() à déplacer ici
    const USB_CDC_BAUD: u32 = 115200;
    
    let map_err = |e: serialport::Error| BridgeError::SerialOpen {
        port: port_name.to_string(),
        source: std::io::Error::other(e.to_string()),
    };

    #[cfg(windows)]
    {
        let port = serialport::new(port_name, USB_CDC_BAUD)
            .timeout(std::time::Duration::from_millis(1))
            .open_native()
            .map_err(map_err)?;
        crate::platform::configure_serial_low_latency(&port);
        Ok(Box::new(port))
    }

    #[cfg(not(windows))]
    {
        serialport::new(port_name, USB_CDC_BAUD)
            .timeout(std::time::Duration::from_millis(1))
            .open()
            .map_err(map_err)
    }
}
```

**Ajouter fonction helper:**

```rust
fn matches_device(port: &SerialPortInfo, config: &DeviceConfig) -> bool {
    match &port.port_type {
        SerialPortType::UsbPort(usb) => {
            usb.vid == config.vid && config.pid_list.contains(&usb.pid)
        }
        _ => {
            // Fallback: pattern de nom si disponible
            config.name_hint.current()
                .map(|hint| port.port_name.contains(hint))
                .unwrap_or(false)
        }
    }
}
```

**Modifier `impl Transport for SerialTransport`:**
- Ligne 59: Remplacer `serial::open(&self.port_name)?` par `Self::open(&self.port_name)?`

**Mettre à jour les doc comments:**
- Ligne 23: Remplacer "Teensy/USB CDC" par "USB CDC serial"
- Lignes 32-33: Supprimer références Teensy dans l'exemple

---

## PHASE 4: Supprimer le Module serial/

### Fichier: `src/serial/mod.rs`
**ACTION: SUPPRIMER CE FICHIER**

### Fichier: `src/main.rs`
- Ligne 31: Supprimer `mod serial;`
- Lignes 114-115: Remplacer:
  ```rust
  // AVANT
  eprintln!("Auto-detecting Teensy...");
  serial::detect_teensy()?
  
  // APRÈS
  eprintln!("Auto-detecting device...");
  // Charger preset depuis config
  let cfg = config::load();
  let device_config = cfg.bridge.device_preset
      .as_ref()
      .and_then(|name| config::load_device_preset(name).ok())
      .ok_or(BridgeError::NoDeviceFound)?;
  SerialTransport::detect(&device_config)?
  ```

### Fichier: `src/bridge/mod.rs`
- Ligne 42: Supprimer `use crate::serial;`
- Ligne 191-203: Remplacer `serial::detect_teensy()` par logique avec config

### Fichier: `src/bridge_state.rs`
- Ligne 9: Supprimer `use crate::{serial, service};` → `use crate::service;`
- Ligne 391: Remplacer `serial::detect_teensy().ok()` par nouvelle logique

---

## PHASE 5: Renommer TeensyCodec → CobsDebugCodec

### Fichier: `src/codec/teensy.rs`
**ACTION: RENOMMER EN `src/codec/cobs_debug.rs`**

**Modifications dans le fichier:**
- Ligne 1: `//! COBS+Debug codec for Serial USB communication`
- Ligne 11-15: Remplacer toutes les occurrences de "Teensy" par termes génériques
- Ligne 16: `pub struct CobsDebugCodec {`
- Ligne 22-24: `impl CobsDebugCodec { ... pub fn new(...) -> Self`
- Ligne 33: `impl Default for CobsDebugCodec`
- Ligne 39: `impl Codec for CobsDebugCodec`
- Tests (lignes 94, 110, 126, 140): Renommer `TeensyCodec` → `CobsDebugCodec`

### Fichier: `src/codec/mod.rs`
- Ligne 17: `pub mod cobs_debug;` (était `pub mod teensy;`)
- Ligne 20: `pub use cobs_debug::CobsDebugCodec;` (était `pub use teensy::TeensyCodec;`)

### Fichier: `src/codec/oc_log.rs`
- Ligne 3: Remplacer "Teensy firmware" par "firmware"

### Fichier: `src/bridge/mod.rs`
- Ligne 34: `use crate::codec::{RawCodec, CobsDebugCodec};`
- Ligne 241: `CobsDebugCodec::new(UDP_BUFFER_SIZE),`

### Fichier: `src/bridge/session.rs`
- Lignes 40, 44, 51, 98, 109: Mettre à jour les doc comments (supprimer "Teensy")

---

## PHASE 6: Erreurs Génériques

### Fichier: `src/error.rs`

**Remplacer lignes 38-41:**
```rust
// AVANT
/// No Teensy device found
NoTeensyFound,
/// Multiple Teensy devices found
MultipleTeensyFound { count: usize },

// APRÈS
/// No device found matching configuration
NoDeviceFound,
/// Multiple devices found matching configuration
MultipleDevicesFound { count: usize },
```

**Remplacer lignes 82-84:**
```rust
// AVANT
Self::NoTeensyFound => write!(f, "No Teensy found"),
Self::MultipleTeensyFound { count } => {
    write!(f, "Multiple Teensy found ({})", count)
}

// APRÈS
Self::NoDeviceFound => write!(f, "No device found"),
Self::MultipleDevicesFound { count } => {
    write!(f, "Multiple devices found ({})", count)
}
```

---

## PHASE 7: UI - Sélecteur de Preset

### Fichier: `src/app.rs`

**Modifier les messages (lignes 102, 109):**
```rust
// AVANT
app.logs.add(LogEntry::system(format!("Teensy detected: {}", port)));
app.logs.add(LogEntry::system("No Teensy detected"));

// APRÈS  
app.logs.add(LogEntry::system(format!("Device detected: {}", port)));
app.logs.add(LogEntry::system("No device detected"));
```

**Ajouter support preset dans `App`:**
- Ajouter champ `available_presets: Vec<String>` (chargé au démarrage)
- Ajouter méthode `select_preset(&mut self, name: &str)`

### Fichier: `src/popup/mode_settings.rs`

**Ajouter champ pour preset:**
```rust
pub struct ModeSettings {
    // ... existing fields ...
    pub device_preset: Option<String>,
    pub available_presets: Vec<String>,
}
```

**Ajouter `ModeField::DevicePreset`** dans l'enum et implémenter navigation.

---

## PHASE 8: Fichiers de Configuration

### Nouveau fichier: `config/default.toml`

```toml
# Open Control Bridge - Default Configuration
# This file is embedded in the binary and provides base settings.
# User settings in config.toml override these values.

[bridge]
transport_mode = "auto"
serial_port = ""
udp_port = 9000
log_broadcast_port = 9002
controller_name = "Controller"
host_name = "Host"
auto_timeout_secs = 5
# device_preset = "teensy"  # Uncomment to enable auto-detection

[logs]
max_entries = 200
export_max = 2000

[ui]
default_filter = "All"
```

### Nouveau fichier: `config/devices/teensy.toml`

```toml
# Teensy USB Development Board
# https://www.pjrc.com/teensy/

[device]
name = "Teensy"
vid = 0x16C0
pid_list = [0x0483, 0x0486, 0x0487, 0x0489]

[device.name_hint]
macos = "usbmodem"
linux = "ttyACM"
```

### Fichier: `src/service/linux.rs`

**Modifier lignes 105-147 (ensure_serial_access):**
- Rendre la règle udev configurable via le preset chargé
- Ou généraliser: créer règle pour le VID du preset actif

---

## PHASE 9: Mise à jour Documentation

### Fichier: `src/main.rs`
- Lignes 4-5: Mettre à jour le doc comment du module

### Fichier: `src/bridge/mod.rs`
- Ligne 8: Remplacer "Teensy" par "Controller" dans l'ASCII art
- Ligne 180: Mettre à jour doc comment

### Fichier: `src/constants.rs`
- Ligne 22: Remplacer "Teensy reconnection" par "Serial reconnection"

### Fichier: `src/transport/serial.rs`
- Mettre à jour tous les doc comments

---

## Ordre d'Exécution Recommandé

1. **Phase 1** - Structures config (pas de breaking change)
2. **Phase 2** - Chargement presets (pas de breaking change)  
3. **Phase 8** - Créer fichiers config (nécessaire pour Phase 3)
4. **Phase 3** - Détection générique (modifie transport/serial.rs)
5. **Phase 4** - Supprimer serial/ (dépend de Phase 3)
6. **Phase 5** - Renommer TeensyCodec (indépendant)
7. **Phase 6** - Erreurs génériques (doit suivre Phase 4)
8. **Phase 7** - UI preset selector (dépend de Phase 1-2)
9. **Phase 9** - Documentation (en dernier)

---

## Tests à Maintenir/Ajouter

- `config.rs`: Tests pour `list_device_presets()`, `load_device_preset()`
- `transport/serial.rs`: Tests pour `detect()`, `matches_device()`
- `codec/cobs_debug.rs`: Renommer les tests existants
- Tests d'intégration avec différents presets

---

## Fichiers à Supprimer

1. `src/serial/mod.rs` - fusionné dans `transport/serial.rs`

## Fichiers à Renommer

1. `src/codec/teensy.rs` → `src/codec/cobs_debug.rs`

## Nouveaux Fichiers

1. `config/default.toml`
2. `config/devices/teensy.toml`
