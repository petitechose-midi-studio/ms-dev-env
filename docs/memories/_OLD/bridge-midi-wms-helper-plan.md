# Plan d'Implementation - MIDI Windows via Helper C#

> Date: 2025-01-15  
> Status: Plan detaille, pret pour implementation  
> Approche: Helper C# pour Windows MIDI Services + Named Pipe

## Resume de l'approche

```
┌─────────────────────────────────────────────────────────────────────┐
│                         Windows                                      │
│                                                                      │
│  ┌──────────────┐    Named Pipe    ┌────────────────────────────┐  │
│  │   Bridge     │◄────────────────►│   midi-helper.exe (C#)     │  │
│  │   (Rust)     │                  │                            │  │
│  │              │                  │  ┌──────────────────────┐  │  │
│  │  - Spawn     │                  │  │  Virtual Device WMS  │  │  │
│  │  - Send MIDI │                  │  │  "Open Control"      │  │  │
│  │  - Recv MIDI │                  │  │                      │  │  │
│  └──────┬───────┘                  │  │ Device    Client     │  │  │
│         │                          │  │ Endpoint  Endpoint   │  │  │
│         │ WebSocket                │  │ (prive)   (DAWs)     │  │  │
│         ▼                          │  └──────────────────────┘  │  │
│  ┌──────────────┐                  └─────────────┬──────────────┘  │
│  │  Simulateur  │                                │                  │
│  │  (Browser)   │                                │ MIDI             │
│  └──────────────┘                                ▼                  │
│                                           ┌──────────────┐          │
│                                           │  DAW         │          │
│                                           │  (Bitwig,    │          │
│                                           │   Ableton)   │          │
│                                           └──────────────┘          │
└─────────────────────────────────────────────────────────────────────┘
```

## Pourquoi cette approche ?

| Critere | Valeur |
|---------|--------|
| **Pas de feedback** | Architecture device/client separee (comme hardware) |
| **1 seul port visible** | Les DAWs voient "Open Control", pas 2 ports loopback |
| **Simplicite** | C# est le langage le mieux supporte par WMS |
| **Maintenance** | Code C# suit les exemples officiels Microsoft |

---

## Structure des fichiers

```
open-control/
├── bridge/                          (Rust - existant)
│   ├── Cargo.toml                   # Ajouter tokio features
│   └── src/
│       ├── main.rs                  # Ajouter mod midi
│       ├── config.rs                # Ajouter MidiConfig
│       └── midi/                    # NOUVEAU
│           ├── mod.rs               # API publique
│           ├── error.rs             # MidiError
│           ├── message.rs           # MidiMessage enum
│           ├── pipe_client.rs       # Client Named Pipe
│           └── helper.rs            # Spawn/manage midi-helper
│
└── tools/
    └── midi-helper/                 # NOUVEAU (C#)
        ├── midi-helper.csproj
        ├── Program.cs               # Entry point
        ├── VirtualDevice.cs         # WMS Virtual Device
        ├── PipeServer.cs            # Named Pipe server
        └── Protocol.cs              # Message serialization
```

---

## Protocole de communication (Named Pipe)

### Nom du pipe
```
\\.\pipe\open-control-midi
```

### Format des messages

```
┌──────────────────┬─────────────────────────────────┐
│ Length (4 bytes) │ Payload (N bytes)               │
│ Little-endian    │                                 │
└──────────────────┴─────────────────────────────────┘
```

### Types de messages

```
Direction: Bridge → Helper
─────────────────────────────
[0x01] [channel] [status] [data1] [data2?]  = MIDI message to send
[0x02]                                       = Ping (keepalive)
[0xFF]                                       = Shutdown request

Direction: Helper → Bridge
─────────────────────────────
[0x01] [channel] [status] [data1] [data2?]  = MIDI message received from DAW
[0x02]                                       = Pong (response to ping)
[0x10] [string...]                           = Ready (device created, name follows)
[0xFE] [string...]                           = Error (message follows)
[0xFD]                                       = Service not available
```

### Exemple concret

```
Bridge envoie Note On (channel 0, note 60, velocity 100):
  Length: 00 00 00 04 (4 bytes)
  Payload: 01 90 3C 64
           │  │  │  └── velocity 100
           │  │  └───── note 60
           │  └──────── status 0x90 (Note On channel 0)
           └─────────── type 0x01 (MIDI message)

Helper repond Ready:
  Length: 00 00 00 0D (13 bytes)
  Payload: 10 4F 70 65 6E 20 43 6F 6E 74 72 6F 6C
           │  └─────────────────────────────────── "Open Control"
           └────────────────────────────────────── type 0x10 (Ready)
```

---

## Code C# - midi-helper

### midi-helper.csproj

```xml
<Project Sdk="Microsoft.NET.Sdk">
  <PropertyGroup>
    <OutputType>Exe</OutputType>
    <TargetFramework>net8.0-windows10.0.22621.0</TargetFramework>
    <Platforms>x64;ARM64</Platforms>
    <RuntimeIdentifiers>win-x64;win-arm64</RuntimeIdentifiers>
    <SupportedOSPlatformVersion>10.0.22621.0</SupportedOSPlatformVersion>
    <ImplicitUsings>enable</ImplicitUsings>
    <Nullable>enable</Nullable>
    <PublishSingleFile>true</PublishSingleFile>
    <SelfContained>true</SelfContained>
  </PropertyGroup>

  <ItemGroup>
    <PackageReference Include="Microsoft.Windows.Devices.Midi2" Version="*-*" />
  </ItemGroup>
</Project>
```

### Program.cs

```csharp
using System.IO.Pipes;

namespace OpenControl.MidiHelper;

class Program
{
    const string PipeName = "open-control-midi";
    const string DeviceName = "Open Control";
    const string ProductId = "OPENCTRL_001";

    static async Task<int> Main(string[] args)
    {
        Console.WriteLine($"[midi-helper] Starting...");

        // 1. Create Virtual Device
        using var device = new VirtualDevice();
        if (!device.Initialize(DeviceName, ProductId))
        {
            Console.Error.WriteLine("[midi-helper] Failed to initialize virtual device");
            return 1;
        }

        Console.WriteLine($"[midi-helper] Virtual device '{DeviceName}' created");

        // 2. Start pipe server and handle connections
        var cts = new CancellationTokenSource();
        Console.CancelKeyPress += (_, e) => { e.Cancel = true; cts.Cancel(); };

        try
        {
            await RunPipeServer(device, cts.Token);
        }
        catch (OperationCanceledException)
        {
            Console.WriteLine("[midi-helper] Shutting down...");
        }

        return 0;
    }

    static async Task RunPipeServer(VirtualDevice device, CancellationToken ct)
    {
        while (!ct.IsCancellationRequested)
        {
            await using var server = new NamedPipeServerStream(
                PipeName,
                PipeDirection.InOut,
                1,  // Single instance
                PipeTransmissionMode.Byte,
                PipeOptions.Asynchronous);

            Console.WriteLine("[midi-helper] Waiting for bridge connection...");
            await server.WaitForConnectionAsync(ct);
            Console.WriteLine("[midi-helper] Bridge connected");

            try
            {
                await HandleConnection(server, device, ct);
            }
            catch (IOException ex)
            {
                Console.WriteLine($"[midi-helper] Connection lost: {ex.Message}");
            }
        }
    }

    static async Task HandleConnection(
        NamedPipeServerStream pipe, 
        VirtualDevice device, 
        CancellationToken ct)
    {
        // Send Ready message
        await Protocol.SendReady(pipe, DeviceName, ct);

        // Setup bidirectional message handling
        var readTask = ReadFromBridge(pipe, device, ct);
        var writeTask = WriteTobridge(pipe, device, ct);

        await Task.WhenAny(readTask, writeTask);
    }

    static async Task ReadFromBridge(
        Stream pipe, 
        VirtualDevice device, 
        CancellationToken ct)
    {
        while (!ct.IsCancellationRequested)
        {
            var message = await Protocol.ReceiveMessage(pipe, ct);
            
            switch (message.Type)
            {
                case MessageType.MidiData:
                    device.SendMidi(message.Data);
                    break;
                case MessageType.Ping:
                    await Protocol.SendPong(pipe, ct);
                    break;
                case MessageType.Shutdown:
                    return;
            }
        }
    }

    static async Task WriteTobridge(
        Stream pipe, 
        VirtualDevice device, 
        CancellationToken ct)
    {
        await foreach (var midiData in device.IncomingMessages.ReadAllAsync(ct))
        {
            await Protocol.SendMidiData(pipe, midiData, ct);
        }
    }
}
```

### VirtualDevice.cs

```csharp
using System.Threading.Channels;
using Microsoft.Windows.Devices.Midi2;
using Microsoft.Windows.Devices.Midi2.Endpoints.Virtual;
using Microsoft.Windows.Devices.Midi2.Initialization;
using Microsoft.Windows.Devices.Midi2.Messages;

namespace OpenControl.MidiHelper;

public class VirtualDevice : IDisposable
{
    private MidiDesktopAppSdkInitializer? _initializer;
    private MidiSession? _session;
    private MidiVirtualDevice? _device;
    private MidiEndpointConnection? _connection;
    
    private readonly Channel<byte[]> _incomingMessages = 
        Channel.CreateUnbounded<byte[]>();

    public ChannelReader<byte[]> IncomingMessages => _incomingMessages.Reader;

    public bool Initialize(string deviceName, string productId)
    {
        try
        {
            // 1. Initialize SDK
            _initializer = MidiDesktopAppSdkInitializer.Create();
            if (!_initializer.InitializeSdkRuntime())
            {
                Console.Error.WriteLine("Failed to initialize MIDI SDK runtime");
                return false;
            }
            if (!_initializer.EnsureServiceAvailable())
            {
                Console.Error.WriteLine("MIDI service not available");
                return false;
            }

            // 2. Create device config
            var config = CreateDeviceConfig(deviceName, productId);

            // 3. Create session
            _session = MidiSession.Create(deviceName);
            if (_session == null) return false;

            // 4. Create virtual device
            _device = MidiVirtualDeviceManager.CreateVirtualDevice(config);
            if (_device == null) return false;

            // 5. Connect to device endpoint (private, not visible to DAWs)
            _connection = _session.CreateEndpointConnection(
                _device.DeviceEndpointDeviceId);
            if (_connection == null) return false;

            // 6. Add device as message processor
            _connection.AddMessageProcessingPlugin(_device);

            // 7. Handle incoming messages from DAWs
            _connection.MessageReceived += OnMessageReceived;

            // 8. Open connection (device becomes visible)
            if (!_connection.Open())
            {
                Console.Error.WriteLine("Failed to open connection");
                return false;
            }

            return true;
        }
        catch (Exception ex)
        {
            Console.Error.WriteLine($"Init error: {ex.Message}");
            return false;
        }
    }

    private static MidiVirtualDeviceCreationConfig CreateDeviceConfig(
        string name, string productId)
    {
        var endpointInfo = new MidiDeclaredEndpointInfo
        {
            Name = name,
            ProductInstanceId = productId,
            SpecificationVersionMajor = 1,
            SpecificationVersionMinor = 1,
            SupportsMidi10Protocol = true,
            SupportsMidi20Protocol = false,  // MIDI 1.0 suffit
            HasStaticFunctionBlocks = true
        };

        var config = new MidiVirtualDeviceCreationConfig(
            name,
            "Open Control Bridge virtual MIDI device",
            "Open Control",
            endpointInfo,
            new MidiDeclaredDeviceIdentity(),
            new MidiEndpointUserSuppliedInfo { Name = name }
        );

        // Add function block (required)
        var block = new MidiFunctionBlock
        {
            Number = 0,
            Name = "MIDI",
            IsActive = true,
            FirstGroup = new MidiGroup(0),
            GroupCount = 1,
            Direction = MidiFunctionBlockDirection.Bidirectional,
            RepresentsMidi10Connection = 
                MidiFunctionBlockRepresentsMidi10Connection.YesBandwidthUnrestricted
        };
        config.FunctionBlocks.Add(block);

        return config;
    }

    private void OnMessageReceived(
        IMidiMessageReceivedEventSource sender, 
        MidiMessageReceivedEventArgs args)
    {
        // Convert UMP to MIDI 1.0 bytes
        var bytes = UmpToMidi1(args);
        if (bytes != null)
        {
            _incomingMessages.Writer.TryWrite(bytes);
        }
    }

    public void SendMidi(byte[] midi1Data)
    {
        if (_connection == null) return;

        // Convert MIDI 1.0 to UMP and send
        var ump = Midi1ToUmp(midi1Data);
        if (ump.HasValue)
        {
            _connection.SendSingleMessageWords(0, ump.Value);
        }
    }

    private static byte[]? UmpToMidi1(MidiMessageReceivedEventArgs args)
    {
        // UMP Type 2 = MIDI 1.0 Channel Voice Message
        var word = args.PeekFirstWord();
        var messageType = (word >> 28) & 0x0F;
        
        if (messageType != 2) return null;  // Only handle Type 2 (MIDI 1.0)

        var status = (byte)((word >> 16) & 0xFF);
        var data1 = (byte)((word >> 8) & 0x7F);
        var data2 = (byte)(word & 0x7F);

        // Determine message length based on status
        var statusHigh = status & 0xF0;
        return statusHigh switch
        {
            0xC0 or 0xD0 => new[] { status, data1 },  // Program Change, Channel Pressure
            _ => new[] { status, data1, data2 }       // All others are 3 bytes
        };
    }

    private static uint? Midi1ToUmp(byte[] data)
    {
        if (data.Length < 2) return null;

        var status = data[0];
        var data1 = data.Length > 1 ? data[1] : (byte)0;
        var data2 = data.Length > 2 ? data[2] : (byte)0;

        // UMP Type 2 = MIDI 1.0 Channel Voice Message
        // Format: 0x2GCC_DDDD where G=group, CC=status+channel, DDDD=data
        uint ump = 0x20000000;  // Type 2, Group 0
        ump |= (uint)status << 16;
        ump |= (uint)data1 << 8;
        ump |= data2;

        return ump;
    }

    public void Dispose()
    {
        _incomingMessages.Writer.Complete();
        
        if (_connection != null && _session != null)
        {
            _session.DisconnectEndpointConnection(_connection.ConnectionId);
        }
        _session?.Dispose();
        _initializer?.Dispose();
    }
}
```

### Protocol.cs

```csharp
namespace OpenControl.MidiHelper;

public enum MessageType : byte
{
    MidiData = 0x01,
    Ping = 0x02,
    Ready = 0x10,
    Pong = 0x02,
    Error = 0xFE,
    ServiceUnavailable = 0xFD,
    Shutdown = 0xFF
}

public record Message(MessageType Type, byte[] Data);

public static class Protocol
{
    public static async Task SendReady(Stream stream, string deviceName, CancellationToken ct)
    {
        var nameBytes = System.Text.Encoding.UTF8.GetBytes(deviceName);
        var payload = new byte[1 + nameBytes.Length];
        payload[0] = (byte)MessageType.Ready;
        nameBytes.CopyTo(payload, 1);
        await SendRaw(stream, payload, ct);
    }

    public static async Task SendPong(Stream stream, CancellationToken ct)
    {
        await SendRaw(stream, new[] { (byte)MessageType.Pong }, ct);
    }

    public static async Task SendMidiData(Stream stream, byte[] midiData, CancellationToken ct)
    {
        var payload = new byte[1 + midiData.Length];
        payload[0] = (byte)MessageType.MidiData;
        midiData.CopyTo(payload, 1);
        await SendRaw(stream, payload, ct);
    }

    public static async Task SendError(Stream stream, string message, CancellationToken ct)
    {
        var msgBytes = System.Text.Encoding.UTF8.GetBytes(message);
        var payload = new byte[1 + msgBytes.Length];
        payload[0] = (byte)MessageType.Error;
        msgBytes.CopyTo(payload, 1);
        await SendRaw(stream, payload, ct);
    }

    public static async Task<Message> ReceiveMessage(Stream stream, CancellationToken ct)
    {
        var payload = await ReceiveRaw(stream, ct);
        if (payload.Length == 0)
            throw new IOException("Empty message received");

        var type = (MessageType)payload[0];
        var data = payload.Length > 1 ? payload[1..] : Array.Empty<byte>();
        return new Message(type, data);
    }

    private static async Task SendRaw(Stream stream, byte[] payload, CancellationToken ct)
    {
        var lenBytes = BitConverter.GetBytes((uint)payload.Length);
        if (!BitConverter.IsLittleEndian) Array.Reverse(lenBytes);
        
        await stream.WriteAsync(lenBytes, ct);
        await stream.WriteAsync(payload, ct);
        await stream.FlushAsync(ct);
    }

    private static async Task<byte[]> ReceiveRaw(Stream stream, CancellationToken ct)
    {
        var lenBytes = new byte[4];
        await ReadExactly(stream, lenBytes, ct);
        if (!BitConverter.IsLittleEndian) Array.Reverse(lenBytes);
        
        var len = BitConverter.ToUInt32(lenBytes);
        if (len > 1024 * 1024) // 1MB max
            throw new IOException($"Message too large: {len}");

        var payload = new byte[len];
        await ReadExactly(stream, payload, ct);
        return payload;
    }

    private static async Task ReadExactly(Stream stream, byte[] buffer, CancellationToken ct)
    {
        var offset = 0;
        while (offset < buffer.Length)
        {
            var read = await stream.ReadAsync(
                buffer.AsMemory(offset, buffer.Length - offset), ct);
            if (read == 0)
                throw new EndOfStreamException("Pipe closed");
            offset += read;
        }
    }
}
```

---

## Code Rust - Bridge

### Cargo.toml (ajouts)

```toml
[dependencies]
# Existant...
tokio = { version = "1", features = ["net", "io-util", "process", "sync", "rt-multi-thread"] }

[target.'cfg(windows)'.dependencies]
windows-sys = { version = "0.59", features = ["Win32_Foundation"] }
```

### src/midi/mod.rs

```rust
//! MIDI virtual device support for Open Control Bridge
//!
//! Windows: Uses midi-helper.exe (C#) for WMS Virtual Device
//! macOS/Linux: Uses midir for native virtual ports

pub mod error;
pub mod message;

#[cfg(windows)]
pub mod helper;
#[cfg(windows)]
pub mod pipe_client;

#[cfg(unix)]
pub mod midir_backend;

pub use error::{MidiError, Result};
pub use message::MidiMessage;

use tokio::sync::mpsc;

/// MIDI port abstraction
pub struct MidiPort {
    pub name: String,
    /// Send MIDI messages to DAWs
    pub tx: mpsc::Sender<Vec<u8>>,
    /// Receive MIDI messages from DAWs
    pub rx: mpsc::Receiver<Vec<u8>>,
}

/// Create a MIDI port for the current platform
pub async fn create_port(name: &str) -> Result<MidiPort> {
    #[cfg(windows)]
    {
        helper::create_port(name).await
    }
    
    #[cfg(unix)]
    {
        midir_backend::create_port(name).await
    }
}
```

### src/midi/error.rs

```rust
use std::fmt;

#[derive(Debug)]
pub enum MidiError {
    HelperNotFound { path: String },
    HelperStartFailed { reason: String },
    HelperDied { exit_code: Option<i32> },
    PipeConnectFailed { reason: String },
    PipeClosed,
    ProtocolError { reason: String },
    ServiceUnavailable,
    InitFailed { reason: String },
}

impl fmt::Display for MidiError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::HelperNotFound { path } => 
                write!(f, "midi-helper not found at: {}", path),
            Self::HelperStartFailed { reason } => 
                write!(f, "Failed to start midi-helper: {}", reason),
            Self::HelperDied { exit_code } => 
                write!(f, "midi-helper exited unexpectedly: {:?}", exit_code),
            Self::PipeConnectFailed { reason } => 
                write!(f, "Failed to connect to midi-helper: {}", reason),
            Self::PipeClosed => 
                write!(f, "Connection to midi-helper lost"),
            Self::ProtocolError { reason } => 
                write!(f, "Protocol error: {}", reason),
            Self::ServiceUnavailable => 
                write!(f, "Windows MIDI Services not available"),
            Self::InitFailed { reason } => 
                write!(f, "MIDI init failed: {}", reason),
        }
    }
}

impl std::error::Error for MidiError {}

pub type Result<T> = std::result::Result<T, MidiError>;
```

### src/midi/pipe_client.rs

```rust
//! Named Pipe client for Windows

use super::error::{MidiError, Result};
use std::time::Duration;
use tokio::io::{AsyncReadExt, AsyncWriteExt};
use tokio::net::windows::named_pipe::ClientOptions;
use tokio::time;
use windows_sys::Win32::Foundation::ERROR_PIPE_BUSY;

const PIPE_NAME: &str = r"\\.\pipe\open-control-midi";
const CONNECT_TIMEOUT: Duration = Duration::from_secs(10);
const RETRY_DELAY: Duration = Duration::from_millis(100);

pub struct PipeClient {
    pipe: tokio::net::windows::named_pipe::NamedPipeClient,
}

impl PipeClient {
    /// Connect to the midi-helper pipe with retries
    pub async fn connect() -> Result<Self> {
        let start = std::time::Instant::now();
        
        loop {
            match ClientOptions::new().open(PIPE_NAME) {
                Ok(pipe) => {
                    return Ok(Self { pipe });
                }
                Err(e) if e.raw_os_error() == Some(ERROR_PIPE_BUSY as i32) => {
                    // Pipe busy, retry
                }
                Err(e) if e.kind() == std::io::ErrorKind::NotFound => {
                    // Pipe not yet created, retry
                }
                Err(e) => {
                    return Err(MidiError::PipeConnectFailed {
                        reason: e.to_string(),
                    });
                }
            }

            if start.elapsed() > CONNECT_TIMEOUT {
                return Err(MidiError::PipeConnectFailed {
                    reason: "Connection timeout".into(),
                });
            }

            time::sleep(RETRY_DELAY).await;
        }
    }

    /// Send a length-prefixed message
    pub async fn send(&mut self, data: &[u8]) -> Result<()> {
        let len = data.len() as u32;
        self.pipe
            .write_all(&len.to_le_bytes())
            .await
            .map_err(|_| MidiError::PipeClosed)?;
        self.pipe
            .write_all(data)
            .await
            .map_err(|_| MidiError::PipeClosed)?;
        Ok(())
    }

    /// Receive a length-prefixed message
    pub async fn receive(&mut self) -> Result<Vec<u8>> {
        let mut len_buf = [0u8; 4];
        self.pipe
            .read_exact(&mut len_buf)
            .await
            .map_err(|_| MidiError::PipeClosed)?;
        
        let len = u32::from_le_bytes(len_buf) as usize;
        if len > 1024 * 1024 {
            return Err(MidiError::ProtocolError {
                reason: format!("Message too large: {}", len),
            });
        }

        let mut buf = vec![0u8; len];
        self.pipe
            .read_exact(&mut buf)
            .await
            .map_err(|_| MidiError::PipeClosed)?;
        
        Ok(buf)
    }

    /// Send MIDI data (type 0x01)
    pub async fn send_midi(&mut self, data: &[u8]) -> Result<()> {
        let mut payload = vec![0x01];  // MessageType::MidiData
        payload.extend_from_slice(data);
        self.send(&payload).await
    }

    /// Send ping (type 0x02)
    pub async fn send_ping(&mut self) -> Result<()> {
        self.send(&[0x02]).await
    }

    /// Send shutdown (type 0xFF)
    pub async fn send_shutdown(&mut self) -> Result<()> {
        self.send(&[0xFF]).await
    }
}

/// Message types from helper
#[derive(Debug)]
pub enum HelperMessage {
    MidiData(Vec<u8>),
    Ready(String),
    Pong,
    Error(String),
    ServiceUnavailable,
}

impl HelperMessage {
    pub fn parse(data: &[u8]) -> Result<Self> {
        if data.is_empty() {
            return Err(MidiError::ProtocolError {
                reason: "Empty message".into(),
            });
        }

        match data[0] {
            0x01 => Ok(Self::MidiData(data[1..].to_vec())),
            0x02 => Ok(Self::Pong),
            0x10 => {
                let name = String::from_utf8_lossy(&data[1..]).to_string();
                Ok(Self::Ready(name))
            }
            0xFE => {
                let msg = String::from_utf8_lossy(&data[1..]).to_string();
                Ok(Self::Error(msg))
            }
            0xFD => Ok(Self::ServiceUnavailable),
            other => Err(MidiError::ProtocolError {
                reason: format!("Unknown message type: 0x{:02X}", other),
            }),
        }
    }
}
```

### src/midi/helper.rs

```rust
//! midi-helper.exe lifecycle management

use super::error::{MidiError, Result};
use super::pipe_client::{HelperMessage, PipeClient};
use super::MidiPort;
use std::path::PathBuf;
use std::process::Stdio;
use tokio::process::{Child, Command};
use tokio::sync::mpsc;

const HELPER_NAME: &str = "midi-helper.exe";

/// Find the midi-helper executable
fn find_helper() -> Result<PathBuf> {
    // 1. Same directory as bridge executable
    if let Ok(exe_path) = std::env::current_exe() {
        let helper_path = exe_path.parent().unwrap().join(HELPER_NAME);
        if helper_path.exists() {
            return Ok(helper_path);
        }
    }

    // 2. tools/midi-helper/ in workspace
    let workspace_path = PathBuf::from("tools/midi-helper/bin/Release/net8.0-windows10.0.22621.0")
        .join(HELPER_NAME);
    if workspace_path.exists() {
        return Ok(workspace_path);
    }

    Err(MidiError::HelperNotFound {
        path: HELPER_NAME.into(),
    })
}

/// Spawn the midi-helper process
async fn spawn_helper() -> Result<Child> {
    let helper_path = find_helper()?;
    
    tracing::info!("Starting midi-helper: {:?}", helper_path);

    let child = Command::new(&helper_path)
        .stdin(Stdio::null())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .map_err(|e| MidiError::HelperStartFailed {
            reason: e.to_string(),
        })?;

    Ok(child)
}

/// Create a MIDI port via midi-helper
pub async fn create_port(name: &str) -> Result<MidiPort> {
    // 1. Spawn helper process
    let mut child = spawn_helper().await?;

    // 2. Connect to helper via Named Pipe
    let mut pipe = PipeClient::connect().await?;

    // 3. Wait for Ready message
    let ready_msg = pipe.receive().await?;
    match HelperMessage::parse(&ready_msg)? {
        HelperMessage::Ready(device_name) => {
            tracing::info!("MIDI device ready: {}", device_name);
        }
        HelperMessage::ServiceUnavailable => {
            return Err(MidiError::ServiceUnavailable);
        }
        HelperMessage::Error(msg) => {
            return Err(MidiError::InitFailed { reason: msg });
        }
        other => {
            return Err(MidiError::ProtocolError {
                reason: format!("Unexpected message: {:?}", other),
            });
        }
    }

    // 4. Create channels for bidirectional communication
    let (tx_to_helper, mut rx_from_bridge) = mpsc::channel::<Vec<u8>>(64);
    let (tx_to_bridge, rx_from_helper) = mpsc::channel::<Vec<u8>>(64);

    // 5. Spawn task to handle communication
    tokio::spawn(async move {
        let result = run_helper_loop(&mut pipe, &mut rx_from_bridge, &tx_to_bridge).await;
        if let Err(e) = result {
            tracing::error!("MIDI helper error: {}", e);
        }
        
        // Cleanup: try to shutdown helper gracefully
        let _ = pipe.send_shutdown().await;
        let _ = child.kill().await;
    });

    Ok(MidiPort {
        name: name.to_string(),
        tx: tx_to_helper,
        rx: rx_from_helper,
    })
}

/// Main communication loop with helper
async fn run_helper_loop(
    pipe: &mut PipeClient,
    rx_from_bridge: &mut mpsc::Receiver<Vec<u8>>,
    tx_to_bridge: &mpsc::Sender<Vec<u8>>,
) -> Result<()> {
    loop {
        tokio::select! {
            // Messages from bridge to send to helper
            Some(midi_data) = rx_from_bridge.recv() => {
                pipe.send_midi(&midi_data).await?;
            }
            
            // Messages from helper to send to bridge
            result = pipe.receive() => {
                let data = result?;
                match HelperMessage::parse(&data)? {
                    HelperMessage::MidiData(midi) => {
                        let _ = tx_to_bridge.send(midi).await;
                    }
                    HelperMessage::Pong => {
                        // Keepalive response, ignore
                    }
                    HelperMessage::Error(msg) => {
                        tracing::error!("Helper error: {}", msg);
                    }
                    _ => {}
                }
            }
        }
    }
}
```

---

## Lifecycle

### Demarrage

```
1. Bridge demarre
2. Bridge verifie si MIDI est active dans config
3. Bridge appelle midi::create_port("Open Control")
4. helper.rs spawn midi-helper.exe
5. midi-helper.exe:
   a. Initialise WMS SDK
   b. Cree Virtual Device "Open Control"
   c. Ouvre Named Pipe server
   d. Attend connexion
6. pipe_client.rs se connecte au pipe
7. midi-helper envoie "Ready"
8. Bridge recoit "Ready", MIDI pret
```

### Fonctionnement

```
Simulateur → Bridge:
1. Simulateur envoie CC via WebSocket
2. Bridge decode le message OC
3. Bridge convertit en MIDI bytes
4. Bridge envoie via mpsc channel
5. helper.rs envoie via Named Pipe
6. midi-helper recoit, convertit en UMP
7. WMS envoie au DAW

DAW → Simulateur:
1. DAW envoie MIDI au Virtual Device
2. midi-helper recoit via WMS callback
3. midi-helper convertit UMP → MIDI 1.0
4. midi-helper envoie via Named Pipe
5. helper.rs recoit, envoie via mpsc
6. Bridge encode en message OC
7. Bridge envoie via WebSocket au simulateur
```

### Arret

```
1. Bridge recoit signal d'arret (Ctrl+C)
2. Bridge drop MidiPort
3. helper.rs envoie "Shutdown" au pipe
4. midi-helper recoit Shutdown
5. midi-helper ferme connexion WMS
6. midi-helper quitte proprement
7. helper.rs kill le process (au cas ou)
```

---

## Build et Distribution

### Build midi-helper

```powershell
cd tools/midi-helper
dotnet publish -c Release -r win-x64 --self-contained
```

Output: `bin/Release/net8.0-windows10.0.22621.0/win-x64/publish/midi-helper.exe`

### Distribution

```
open-control-bridge/
├── bridge.exe           # Rust bridge
├── midi-helper.exe      # C# helper (copier depuis publish/)
└── config.toml
```

---

## Prerequis utilisateur

1. **Windows 11** (22H2 ou plus recent)
2. **Windows MIDI Services** installe
   - Telecharger depuis: https://github.com/microsoft/MIDI/releases
   - Ou via winget: `winget install Microsoft.WindowsMIDIServices`

---

## Fallback si WMS non disponible

Si `midi-helper.exe` renvoie `ServiceUnavailable`:

```rust
// Dans bridge, afficher un message
tracing::warn!(
    "Windows MIDI Services not available. 
     Install from: https://github.com/microsoft/MIDI/releases
     Or use loopMIDI as alternative."
);
```

---

## Tests

### Test manuel

1. Lancer `midi-helper.exe` seul
2. Verifier que "Open Control" apparait dans les devices MIDI Windows
3. Lancer un DAW, connecter au device
4. Verifier bidirectionnel

### Test integration

```rust
#[tokio::test]
#[cfg(windows)]
async fn test_midi_helper_connection() {
    let port = midi::create_port("Test Device").await.unwrap();
    
    // Send a Note On
    port.tx.send(vec![0x90, 60, 100]).await.unwrap();
    
    // Should not crash, helper should handle it
    tokio::time::sleep(Duration::from_millis(100)).await;
}
```

---

## Estimation temps

| Tache | Temps estime |
|-------|--------------|
| Setup projet C# + build | 30 min |
| VirtualDevice.cs | 2h |
| Protocol.cs + PipeServer | 1h |
| Program.cs | 30 min |
| Rust pipe_client.rs | 1h |
| Rust helper.rs | 1h |
| Integration bridge | 1h |
| Tests + debug | 2h |
| **Total** | **~9h** |
