# Plan d'Implementation MIDI Virtuel - OC Bridge

> **INSTRUCTION CRITIQUE - A SUIVRE A CHAQUE DEBUT DE SESSION**
>
> 1. Relire ce fichier EN INTEGRALITE
> 2. Identifier la phase en cours et les taches restantes
> 3. Lire les fichiers impactes par les prochaines etapes AVANT de commencer
> 4. Verifier la coherence avec l'etat actuel du code
> 5. Mettre a jour ce fichier apres chaque modification

---

## Contexte et Objectif

### Probleme
Le simulateur WASM de midi-studio doit pouvoir communiquer en MIDI bidirectionnel avec n'importe quel DAW, sans installation de driver tiers.

### Solution
Utiliser **Windows MIDI Services** (natif Windows 11) pour creer des ports MIDI virtuels visibles par tous les DAWs.

### Architecture Cible

```
┌──────────────────────────────────────────────────────────────────────────┐
│                        MODE LOCAL (./build.sh watch)                      │
│                                                                           │
│  ┌───────────┐   WebMIDI    ┌───────────────┐  WinMIDI   ┌─────────────┐ │
│  │ Browser   │◄────────────►│  Port Virtuel │◄──────────►│  DAW (any)  │ │
│  │ WASM      │              │ "MIDI Studio" │  Services  │             │ │
│  └───────────┘              └───────────────┘            └─────────────┘ │
│                                    ▲                                      │
│                                    │                                      │
│                             ┌──────┴──────┐                              │
│                             │   Bridge    │                              │
│                             │   Rust      │                              │
│                             │  (logging)  │                              │
│                             └─────────────┘                              │
│                                                                           │
│  Lance par: ./build.sh watch                                             │
│  Config: BridgeConfig.toml dans le dossier appelant                      │
└──────────────────────────────────────────────────────────────────────────┘
```

---

## Prerequis

| Prerequis | Version | Notes |
|-----------|---------|-------|
| Windows 11 Insider | Build 26220.7344+ | Beta ou Dev channel |
| Windows MIDI Services SDK | 1.0.14-rc.1+ | Installer le SDK Runtime |
| Rust | 1.75+ | Pour windows-rs 0.62 |

### Verification prerequis
```powershell
# Verifier que Windows MIDI Services est actif
midi.exe enum
# Doit lister au moins le loopback interne
```

---

## Statut Global

| Phase | Status | Progress |
|-------|--------|----------|
| Phase 0 - Preparation | ⏳ Pending | 0/3 |
| Phase 1 - Config CWD | ⏳ Pending | 0/2 |
| Phase 2 - Transport MIDI Windows | ⏳ Pending | 0/5 |
| Phase 3 - Mode Local Bridge | ⏳ Pending | 0/3 |
| Phase 4 - Integration build.sh | ⏳ Pending | 0/2 |
| Phase 5 - Tests | ⏳ Pending | 0/3 |
| Phase 6 - Mac/Linux (optionnel) | ⏳ Pending | 0/2 |

---

## Phase 0 : Preparation

### Objectif
Ajouter les dependances necessaires et verifier la faisabilite.

### Fichiers a analyser avant de commencer
- `open-control/bridge/Cargo.toml`
- Documentation Windows MIDI Services: https://microsoft.github.io/MIDI/sdk-reference/

### Taches

- [ ] **0.1** Ajouter features Windows MIDI Services dans Cargo.toml
  ```toml
  [target.'cfg(windows)'.dependencies.windows]
  version = "0.62"
  features = [
      # Existants...
      # A ajouter:
      "Foundation",
      "Foundation_Collections", 
      "Devices_Midi2",
      "Devices_Midi2_Endpoints_Virtual",
  ]
  ```

- [ ] **0.2** Creer fichier de test `src/transport/midi_test.rs`
  - Verifier que les bindings compilent
  - Lister les ports MIDI existants
  - Test: `cargo test --lib midi_test -- --nocapture`

- [ ] **0.3** Documenter les types WinRT necessaires
  ```rust
  // Types a utiliser (namespace Microsoft.Windows.Devices.Midi2)
  // - MidiSession
  // - MidiEndpointConnection
  // - MidiVirtualDeviceManager
  // - MidiVirtualDeviceCreationConfig
  // - MidiDeclaredEndpointInfo
  // - MidiFunctionBlock
  ```

### Critere de validation Phase 0
- [ ] `cargo build` compile sans erreur
- [ ] Test liste les ports MIDI existants

---

## Phase 1 : Config depuis CWD

### Objectif
Permettre au bridge de lire `BridgeConfig.toml` depuis le dossier d'execution.

### Fichiers a modifier
- `open-control/bridge/src/config.rs`
- `open-control/bridge/src/cli.rs`

### Taches

- [ ] **1.1** Modifier `config.rs` pour chercher config dans CWD d'abord
  
  **Fichier:** `src/config.rs`
  
  **Fonction a modifier:** `config_path()`
  
  ```rust
  /// Get the config file path
  /// Priority:
  /// 1. ./BridgeConfig.toml (CWD)
  /// 2. <exe_dir>/config.toml (legacy)
  pub fn config_path() -> Result<PathBuf> {
      // Check CWD first
      let cwd_config = std::env::current_dir()
          .ok()
          .map(|d| d.join("BridgeConfig.toml"));
      
      if let Some(ref path) = cwd_config {
          if path.exists() {
              return Ok(path.clone());
          }
      }
      
      // Fallback to exe directory (existing behavior)
      let exe = std::env::current_exe().map_err(|e| BridgeError::ConfigRead {
          path: PathBuf::from("config.toml"),
          source: e,
      })?;
      let dir = exe.parent().ok_or_else(|| BridgeError::ConfigValidation {
          field: "exe_path",
          reason: "no parent directory".into(),
      })?;
      Ok(dir.join("config.toml"))
  }
  ```

- [ ] **1.2** Ajouter option CLI `--config <path>`
  
  **Fichier:** `src/cli.rs`
  
  ```rust
  #[derive(Parser, Debug, Default)]
  pub struct Cli {
      // Existants...
      
      /// Config file path (default: ./BridgeConfig.toml or <exe>/config.toml)
      #[arg(long, short = 'c', value_name = "PATH")]
      pub config: Option<PathBuf>,
  }
  ```

### Critere de validation Phase 1
- [ ] Bridge lit `./BridgeConfig.toml` si present
- [ ] Bridge fallback sur `config.toml` a cote de l'exe sinon
- [ ] `--config custom.toml` fonctionne

---

## Phase 2 : Transport MIDI Windows

### Objectif
Creer un nouveau transport qui utilise Windows MIDI Services pour creer et gerer un port virtuel.

### Fichiers a creer
- `open-control/bridge/src/transport/midi_virtual.rs`
- `open-control/bridge/src/transport/midi_virtual/device.rs`
- `open-control/bridge/src/transport/midi_virtual/session.rs`

### API Windows MIDI Services a utiliser

```
Microsoft.Windows.Devices.Midi2.Endpoints.Virtual
├── MidiVirtualDeviceManager        # Cree les devices virtuels
├── MidiVirtualDeviceCreationConfig # Config de creation
└── MidiVirtualDevice               # Device cree, gere les messages

Microsoft.Windows.Devices.Midi2
├── MidiSession                     # Session principale
├── MidiEndpointConnection          # Connexion a un endpoint
├── MidiDeclaredEndpointInfo        # Info declaree pour le device
├── MidiFunctionBlock               # Bloc fonctionnel MIDI 2.0
└── MidiMessageReceivedEventArgs    # Event de reception
```

### Taches

- [ ] **2.1** Creer structure de base `midi_virtual.rs`
  
  **Fichier:** `src/transport/midi_virtual.rs`
  
  ```rust
  //! Virtual MIDI port transport using Windows MIDI Services
  //!
  //! Creates a virtual MIDI device that appears in all MIDI applications.
  //! Requires Windows 11 with Windows MIDI Services enabled.
  
  #[cfg(windows)]
  mod windows_impl;
  
  #[cfg(windows)]
  pub use windows_impl::MidiVirtualTransport;
  
  #[cfg(not(windows))]
  compile_error!("MidiVirtualTransport requires Windows MIDI Services");
  ```

- [ ] **2.2** Implementer creation du device virtuel
  
  **Fichier:** `src/transport/midi_virtual/windows_impl.rs`
  
  ```rust
  use windows::Devices::Midi2::*;
  use windows::Devices::Midi2::Endpoints::Virtual::*;
  
  pub struct MidiVirtualTransport {
      name: String,
      session: Option<MidiSession>,
      device: Option<MidiVirtualDevice>,
      connection: Option<MidiEndpointConnection>,
  }
  
  impl MidiVirtualTransport {
      pub fn new(name: &str) -> Self {
          Self {
              name: name.to_string(),
              session: None,
              device: None,
              connection: None,
          }
      }
      
      fn create_device(&mut self) -> Result<()> {
          // 1. Creer la session
          let session = MidiSession::Create(&self.name.clone().into())?;
          
          // 2. Configurer l'endpoint info
          let mut endpoint_info = MidiDeclaredEndpointInfo::new()?;
          endpoint_info.SetName(&self.name.clone().into())?;
          endpoint_info.SetSupportsMidi10Protocol(true)?;
          endpoint_info.SetSupportsMidi20Protocol(true)?;
          
          // 3. Creer la config du device virtuel
          let config = MidiVirtualDeviceCreationConfig::new(
              &self.name.clone().into(),      // name
              &"MIDI Studio Bridge".into(),   // description  
              &"Open Control".into(),         // manufacturer
              &endpoint_info,
          )?;
          
          // 4. Ajouter un function block bidirectionnel
          let mut block = MidiFunctionBlock::new()?;
          block.SetNumber(0)?;
          block.SetIsActive(true)?;
          block.SetName(&"Main".into())?;
          block.SetDirection(MidiFunctionBlockDirection::Bidirectional)?;
          config.FunctionBlocks()?.Append(&block)?;
          
          // 5. Creer le device
          let device = MidiVirtualDeviceManager::CreateVirtualDevice(&config)?;
          
          // 6. Connecter a l'endpoint device-side
          let device_endpoint_id = device.DeviceEndpointDeviceId()?;
          let connection = session.CreateEndpointConnection(&device_endpoint_id)?;
          
          // 7. Ajouter le device comme plugin de traitement
          connection.AddMessageProcessingPlugin(&device)?;
          connection.Open()?;
          
          self.session = Some(session);
          self.device = Some(device);
          self.connection = Some(connection);
          
          Ok(())
      }
  }
  ```

- [ ] **2.3** Implementer trait Transport
  
  ```rust
  impl Transport for MidiVirtualTransport {
      fn spawn(mut self, shutdown: Arc<AtomicBool>) -> Result<TransportChannels> {
          // Creer le device
          self.create_device()?;
          
          // Creer les channels
          let (tx_to_midi, rx_from_bridge) = mpsc::channel::<Bytes>(256);
          let (tx_to_bridge, rx_from_midi) = mpsc::channel::<Bytes>(256);
          
          // Configurer le callback de reception
          let connection = self.connection.as_ref().unwrap();
          let tx = tx_to_bridge.clone();
          connection.MessageReceived(&TypedEventHandler::new(
              move |_, args: &Option<MidiMessageReceivedEventArgs>| {
                  if let Some(args) = args {
                      // Convertir UMP en bytes et envoyer
                      let ump = args.GetMessagePacket()?;
                      let bytes = ump_to_bytes(&ump);
                      let _ = tx.try_send(Bytes::from(bytes));
                  }
                  Ok(())
              }
          ))?;
          
          // Spawn task pour envoyer les messages
          let connection_send = self.connection.clone();
          tokio::spawn(async move {
              while let Some(data) = rx_from_bridge.recv().await {
                  if shutdown.load(Ordering::Relaxed) {
                      break;
                  }
                  // Convertir bytes en UMP et envoyer
                  if let Some(conn) = &connection_send {
                      let msg = bytes_to_ump(&data);
                      let _ = conn.SendSingleMessagePacket(&msg);
                  }
              }
          });
          
          Ok(TransportChannels {
              rx: rx_from_midi,
              tx: tx_to_midi,
          })
      }
  }
  ```

- [ ] **2.4** Implementer conversion MIDI 1.0 <-> UMP
  
  **Fichier:** `src/transport/midi_virtual/conversion.rs`
  
  ```rust
  //! Conversion entre messages MIDI 1.0 (bytes) et UMP (Universal MIDI Packet)
  //!
  //! MIDI 1.0 Channel Voice -> UMP Type 2 (MIDI 1.0 Channel Voice)
  //! UMP Type 2 -> MIDI 1.0 Channel Voice
  
  use windows::Devices::Midi2::*;
  
  /// Convertit des bytes MIDI 1.0 en UMP
  pub fn bytes_to_ump(bytes: &[u8]) -> MidiMessage32 {
      // MIDI 1.0 dans UMP utilise le Message Type 2
      // Format: [status] [data1] [data2?]
      let status = bytes.get(0).copied().unwrap_or(0);
      let data1 = bytes.get(1).copied().unwrap_or(0);
      let data2 = bytes.get(2).copied().unwrap_or(0);
      
      // UMP word: [type:4][group:4][status:8][data1:8][data2:8]
      let word = (0x2u32 << 28)  // Type 2 = MIDI 1.0 Channel Voice
          | ((status as u32) << 16)
          | ((data1 as u32) << 8)
          | (data2 as u32);
      
      MidiMessage32::CreateFromWord(0, word).unwrap()
  }
  
  /// Convertit un UMP en bytes MIDI 1.0
  pub fn ump_to_bytes(msg: &IMidiUniversalPacket) -> Vec<u8> {
      let word = msg.PeekFirstWord().unwrap_or(0);
      let msg_type = (word >> 28) & 0x0F;
      
      match msg_type {
          2 => {
              // Type 2 = MIDI 1.0 Channel Voice
              let status = ((word >> 16) & 0xFF) as u8;
              let data1 = ((word >> 8) & 0xFF) as u8;
              let data2 = (word & 0xFF) as u8;
              
              // Determiner la taille selon le status
              let len = match status & 0xF0 {
                  0xC0 | 0xD0 => 2, // Program Change, Channel Pressure
                  _ => 3,
              };
              
              vec![status, data1, data2][..len].to_vec()
          }
          _ => vec![], // Autres types non supportes pour l'instant
      }
  }
  ```

- [ ] **2.5** Ajouter au module transport
  
  **Fichier:** `src/transport/mod.rs`
  
  ```rust
  pub mod serial;
  pub mod udp;
  
  #[cfg(windows)]
  pub mod midi_virtual;
  
  pub use serial::SerialTransport;
  pub use udp::UdpTransport;
  
  #[cfg(windows)]
  pub use midi_virtual::MidiVirtualTransport;
  ```

### Critere de validation Phase 2
- [ ] `MidiVirtualTransport::new("Test")` compile
- [ ] Le port "Test" apparait dans `midi.exe enum`
- [ ] Le port apparait dans un DAW (Bitwig, Ableton, etc.)
- [ ] Envoi/reception de messages fonctionne

---

## Phase 3 : Mode Local Bridge

### Objectif
Ajouter un mode "local" au bridge qui utilise le transport MIDI virtuel.

### Fichiers a modifier
- `open-control/bridge/src/config.rs`
- `open-control/bridge/src/bridge/runner.rs`
- `open-control/bridge/src/bridge/mod.rs`

### Taches

- [ ] **3.1** Etendre la config avec section [midi]
  
  **Fichier:** `src/config.rs`
  
  ```rust
  /// Bridge operation mode
  #[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize, Default)]
  #[serde(rename_all = "lowercase")]
  pub enum BridgeMode {
      /// Service mode: Serial + UDP, for hardware controller
      #[default]
      Service,
      /// Local mode: Virtual MIDI port, for WASM development
      Local,
  }
  
  #[derive(Debug, Clone, Serialize, Deserialize)]
  #[serde(default)]
  pub struct MidiConfig {
      /// Enable virtual MIDI port
      pub enabled: bool,
      /// Name of the virtual MIDI port
      pub virtual_port_name: String,
  }
  
  impl Default for MidiConfig {
      fn default() -> Self {
          Self {
              enabled: false,
              virtual_port_name: "MIDI Studio".to_string(),
          }
      }
  }
  
  #[derive(Debug, Clone, Serialize, Deserialize)]
  #[serde(default)]
  pub struct Config {
      pub bridge: BridgeConfig,
      pub midi: MidiConfig,  // Nouveau
      pub logs: LogsConfig,
      pub ui: UiConfig,
  }
  ```

- [ ] **3.2** Implementer `local_mode` dans runner.rs
  
  **Fichier:** `src/bridge/runner.rs`
  
  ```rust
  /// Run in local mode (MIDI virtual port)
  ///
  /// Creates a virtual MIDI port for browser/DAW communication.
  /// Used by ./build.sh watch for WASM development.
  #[cfg(windows)]
  pub(super) async fn local_mode(
      config: &Config,
      shutdown: Arc<AtomicBool>,
      stats: Arc<Stats>,
      log_tx: Option<mpsc::Sender<LogEntry>>,
  ) -> Result<()> {
      use crate::transport::MidiVirtualTransport;
      
      let port_name = &config.midi.virtual_port_name;
      
      logging::try_log(&log_tx, LogEntry::system(format!(
          "Local mode: Creating virtual MIDI port '{}'",
          port_name
      )), "local_mode_start");
      
      // Creer le transport MIDI virtuel
      let midi = match MidiVirtualTransport::new(port_name).spawn(shutdown.clone()) {
          Ok(m) => m,
          Err(e) => {
              logging::try_log(&log_tx, LogEntry::system(format!(
                  "Failed to create virtual MIDI port: {}. Is Windows MIDI Services installed?",
                  e
              )), "midi_create_failed");
              return Err(e);
          }
      };
      
      logging::try_log(&log_tx, LogEntry::system(format!(
          "Virtual MIDI port '{}' created. Visible in DAWs.",
          port_name
      )), "midi_created");
      
      // En mode local, on fait juste du monitoring (pass-through)
      // Les messages MIDI vont directement du browser au DAW via le port virtuel
      
      // Boucle de monitoring
      let mut rx = midi.rx;
      while !shutdown.load(Ordering::Relaxed) {
          tokio::select! {
              Some(data) = rx.recv() => {
                  // Log les messages recus (pour debug)
                  stats.controller_received(data.len());
                  logging::try_log(&log_tx, LogEntry::midi_in(&data), "midi_rx");
              }
              _ = tokio::time::sleep(Duration::from_millis(100)) => {
                  // Check shutdown periodiquement
              }
          }
      }
      
      logging::try_log(&log_tx, LogEntry::system("Local mode stopped"), "local_mode_stopped");
      
      Ok(())
  }
  ```

- [ ] **3.3** Router selon le mode dans bridge/mod.rs
  
  **Fichier:** `src/bridge/mod.rs`
  
  ```rust
  pub async fn run(/* ... */) -> Result<()> {
      let config = crate::config::load();
      
      match config.bridge.mode {
          BridgeMode::Service => {
              // Mode existant: Serial + UDP
              match config.bridge.transport_mode {
                  TransportMode::Auto => runner::auto_mode(&config, shutdown, stats, log_tx).await,
                  TransportMode::Serial => runner::serial_mode(&config, shutdown, stats, log_tx).await,
                  TransportMode::Virtual => runner::virtual_mode(&config, shutdown, stats, log_tx).await,
              }
          }
          BridgeMode::Local => {
              // Nouveau mode: MIDI virtuel
              #[cfg(windows)]
              {
                  runner::local_mode(&config, shutdown, stats, log_tx).await
              }
              #[cfg(not(windows))]
              {
                  Err(BridgeError::ConfigValidation {
                      field: "mode",
                      reason: "Local mode requires Windows MIDI Services".into(),
                  })
              }
          }
      }
  }
  ```

### Critere de validation Phase 3
- [ ] Bridge demarre en mode local avec `BridgeConfig.toml`
- [ ] Port virtuel visible dans DAW
- [ ] Logs affichent les messages MIDI transites

---

## Phase 4 : Integration build.sh watch

### Objectif
Lancer automatiquement le bridge en mode local lors de `./build.sh watch`.

### Fichiers a modifier
- `midi-studio/core/desktop/build.sh`
- Creer `midi-studio/core/desktop/BridgeConfig.toml`

### Taches

- [ ] **4.1** Creer BridgeConfig.toml pour dev WASM
  
  **Fichier:** `midi-studio/core/desktop/BridgeConfig.toml`
  
  ```toml
  # Bridge configuration for WASM development
  # Used by ./build.sh watch
  
  [bridge]
  mode = "local"
  controller_name = "MIDI Studio Dev"
  
  [midi]
  enabled = true
  virtual_port_name = "MIDI Studio"
  
  [logs]
  max_entries = 500
  export_max = 5000
  
  [ui]
  default_filter = "All"
  ```

- [ ] **4.2** Modifier build.sh pour lancer le bridge
  
  **Fichier:** `midi-studio/core/desktop/build.sh`
  
  Ajouter dans la section watch:
  
  ```bash
  # ==============================================================================
  # Watch mode with hot reload AND MIDI bridge
  # ==============================================================================
  if $WATCH; then
      # ... code existant pour le serveur HTTP ...
      
      # Start MIDI bridge in background (if available)
      BRIDGE_BIN=$(which oc-bridge 2>/dev/null || echo "")
      BRIDGE_PID=""
      
      if [[ -n "$BRIDGE_BIN" && -f "BridgeConfig.toml" ]]; then
          echo -e "  ${CYAN}→${NC} Starting MIDI bridge..."
          "$BRIDGE_BIN" --headless &
          BRIDGE_PID=$!
          echo -e "  ${GREEN}✓${NC} MIDI bridge started (port: MIDI Studio)"
      else
          echo -e "  ${YELLOW}!${NC} MIDI bridge not available (install oc-bridge for DAW integration)"
      fi
      
      # Cleanup on exit
      cleanup() {
          [[ -n "$BRIDGE_PID" ]] && kill "$BRIDGE_PID" 2>/dev/null
          [[ -n "$SERVER_PID" ]] && kill "$SERVER_PID" 2>/dev/null
          exit
      }
      trap cleanup INT TERM
      
      # ... reste du code watch ...
  fi
  ```

### Critere de validation Phase 4
- [ ] `./build.sh watch` lance le bridge automatiquement
- [ ] Port "MIDI Studio" visible dans DAW pendant le dev
- [ ] Ctrl+C arrete proprement bridge + serveur

---

## Phase 5 : Tests

### Objectif
Valider le fonctionnement end-to-end.

### Taches

- [ ] **5.1** Test unitaire creation device
  
  **Fichier:** `src/transport/midi_virtual/tests.rs`
  
  ```rust
  #[cfg(test)]
  #[cfg(windows)]
  mod tests {
      use super::*;
      
      #[test]
      fn test_midi_virtual_transport_creation() {
          let transport = MidiVirtualTransport::new("Test Port");
          assert!(transport.name == "Test Port");
      }
      
      #[tokio::test]
      async fn test_device_creation() {
          let shutdown = Arc::new(AtomicBool::new(false));
          let result = MidiVirtualTransport::new("Test Device")
              .spawn(shutdown.clone());
          
          // Cleanup
          shutdown.store(true, Ordering::Relaxed);
          
          assert!(result.is_ok(), "Device creation failed: {:?}", result.err());
      }
  }
  ```

- [ ] **5.2** Test integration avec `midi.exe`
  
  ```bash
  # Terminal 1: Lancer le bridge
  cd midi-studio/core/desktop
  oc-bridge --headless
  
  # Terminal 2: Verifier le port
  midi.exe enum | grep "MIDI Studio"
  # Doit afficher le port
  
  # Terminal 3: Monitor
  midi.exe monitor --endpoint "MIDI Studio"
  ```

- [ ] **5.3** Test avec DAW
  
  1. Lancer `./build.sh watch`
  2. Ouvrir Bitwig/Ableton
  3. Configurer "MIDI Studio" comme input/output
  4. Verifier que les notes jouees dans le browser arrivent dans le DAW
  5. Verifier que les notes du DAW arrivent dans le browser

### Critere de validation Phase 5
- [ ] Tests unitaires passent
- [ ] Port visible dans midi.exe
- [ ] Communication bidirectionnelle avec DAW

---

## Phase 6 : Support Mac/Linux (Optionnel)

### Objectif
Etendre le support aux autres plateformes via midir.

### Note
midir supporte les ports virtuels sur Mac (CoreMIDI) et Linux (ALSA), mais PAS sur Windows.
Cette phase utilise midir uniquement pour Mac/Linux.

### Taches

- [ ] **6.1** Ajouter midir comme dependance conditionnelle
  
  ```toml
  [target.'cfg(unix)'.dependencies]
  midir = "0.9"
  ```

- [ ] **6.2** Implementer MidiVirtualTransport pour Unix
  
  ```rust
  #[cfg(unix)]
  mod unix_impl {
      use midir::{MidiInput, MidiOutput};
      
      pub struct MidiVirtualTransport {
          name: String,
          input: Option<MidiInput>,
          output: Option<MidiOutput>,
      }
      
      impl MidiVirtualTransport {
          pub fn new(name: &str) -> Self {
              Self {
                  name: name.to_string(),
                  input: None,
                  output: None,
              }
          }
      }
      
      impl Transport for MidiVirtualTransport {
          fn spawn(mut self, shutdown: Arc<AtomicBool>) -> Result<TransportChannels> {
              // midir permet de creer des ports virtuels sur Mac/Linux
              let input = MidiInput::new(&format!("{} In", self.name))?;
              let output = MidiOutput::new(&format!("{} Out", self.name))?;
              
              // Ouvrir les ports virtuels
              let in_port = input.create_virtual(&self.name, |_, msg, _| {
                  // Callback reception
              }, ())?;
              
              let out_port = output.create_virtual(&self.name)?;
              
              // ... implementation channels ...
          }
      }
  }
  ```

### Critere de validation Phase 6
- [ ] Port virtuel fonctionne sur macOS
- [ ] Port virtuel fonctionne sur Linux

---

## References API

### Windows MIDI Services

| Type | Usage |
|------|-------|
| `MidiSession` | Point d'entree, gere les connexions |
| `MidiVirtualDeviceManager` | Cree les devices virtuels |
| `MidiVirtualDeviceCreationConfig` | Config du device (nom, info, function blocks) |
| `MidiVirtualDevice` | Device cree, recoit/envoie les messages |
| `MidiEndpointConnection` | Connexion a un endpoint |
| `MidiDeclaredEndpointInfo` | Metadata de l'endpoint |
| `MidiFunctionBlock` | Definition d'un bloc MIDI 2.0 |
| `MidiMessage32` | Message UMP 32 bits (MIDI 1.0 dans UMP) |

### Exemple C++ de reference
https://github.com/microsoft/MIDI/blob/main/samples/cpp-winrt/simple-app-to-app-midi/main_simple_app_to_app.cpp

### Documentation Windows MIDI Services
https://microsoft.github.io/MIDI/sdk-reference/

---

## Journal des Modifications

### Session X - YYYY-MM-DD
- Plan cree

---

## Notes Techniques

### Lifecycle du device virtuel

1. **Creation**: `MidiVirtualDeviceManager::CreateVirtualDevice(config)`
   - Le device est cree mais pas encore visible
   
2. **Connexion**: `session.CreateEndpointConnection(device.DeviceEndpointDeviceId())`
   - Connecte au cote "device" du port virtuel
   
3. **Activation**: `connection.Open()`
   - Le port devient visible dans les autres applications
   
4. **Cleanup**: Drop de la session
   - Le port disparait automatiquement

### Format UMP pour MIDI 1.0

```
Word 32 bits:
[31:28] Message Type = 2 (MIDI 1.0 Channel Voice)
[27:24] Group = 0
[23:16] Status byte
[15:8]  Data byte 1
[7:0]   Data byte 2
```

### Erreurs courantes

| Erreur | Cause | Solution |
|--------|-------|----------|
| `E_NOTFOUND` | Windows MIDI Services pas installe | Installer SDK Runtime |
| `E_ACCESSDENIED` | Pas de permission | Verifier Windows Insider |
| Port pas visible | Connection pas ouverte | Appeler `connection.Open()` |
