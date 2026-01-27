"""Typed configuration loading and access.

This module provides dataclasses for the config.toml structure with
full type safety and validation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .result import Err, Ok, Result
from .structured import as_str_dict

__all__ = [
    "Config",
    "BitwigPathsConfig",
    "PortsConfig",
    "ControllerPortsConfig",
    "MidiConfig",
    "PathsConfig",
    "ConfigError",
    "load_config",
    # Port constants
    "CONTROLLER_CORE_NATIVE_PORT",
    "CONTROLLER_CORE_WASM_PORT",
    "CONTROLLER_BITWIG_NATIVE_PORT",
    "CONTROLLER_BITWIG_WASM_PORT",
    "BRIDGE_HARDWARE_PORT",
    "BRIDGE_NATIVE_PORT",
    "BRIDGE_WASM_PORT",
]

# -----------------------------------------------------------------------------
# Default Port Constants
# -----------------------------------------------------------------------------

# Controller ports (app → bridge communication)
CONTROLLER_CORE_NATIVE_PORT = 8000
CONTROLLER_CORE_WASM_PORT = 8100
CONTROLLER_BITWIG_NATIVE_PORT = 8001
CONTROLLER_BITWIG_WASM_PORT = 8101

# Bridge ports (bridge internal)
BRIDGE_HARDWARE_PORT = 9000
BRIDGE_NATIVE_PORT = 9001
BRIDGE_WASM_PORT = 9002


@dataclass(frozen=True, slots=True)
class ConfigError:
    """Error when config cannot be loaded or parsed."""

    message: str
    path: Path | None = None


@dataclass(frozen=True, slots=True)
class ControllerPortsConfig:
    """Controller port configuration."""

    core_native: int = CONTROLLER_CORE_NATIVE_PORT
    core_wasm: int = CONTROLLER_CORE_WASM_PORT
    bitwig_native: int = CONTROLLER_BITWIG_NATIVE_PORT
    bitwig_wasm: int = CONTROLLER_BITWIG_WASM_PORT


@dataclass(frozen=True, slots=True)
class PortsConfig:
    """Port configuration for bridge communication."""

    hardware: int = BRIDGE_HARDWARE_PORT
    native: int = BRIDGE_NATIVE_PORT
    wasm: int = BRIDGE_WASM_PORT
    controller: ControllerPortsConfig = field(default_factory=ControllerPortsConfig)


@dataclass(frozen=True, slots=True)
class MidiConfig:
    """MIDI device name configuration per platform."""

    linux: str = "VirMIDI"
    macos_input: str = "MIDI Studio IN"
    macos_output: str = "MIDI Studio OUT"
    windows: str = "loopMIDI"


@dataclass(frozen=True, slots=True)
class BitwigPathsConfig:
    """Bitwig extension deployment paths per platform.

    Values are user-provided paths (typically absolute). They can include:
    - ~ (home)
    - environment variables (e.g. %USERPROFILE% on Windows)
    """

    linux: str | None = None
    macos: str | None = None
    windows: str | None = None

    def as_dict(self) -> dict[str, str]:
        out: dict[str, str] = {}
        if self.linux:
            out["linux"] = self.linux
        if self.macos:
            out["macos"] = self.macos
        if self.windows:
            out["windows"] = self.windows
        return out


@dataclass(frozen=True, slots=True)
class PathsConfig:
    """Relative paths within workspace."""

    bridge: str = "open-control/bridge"
    extension: str = "midi-studio/plugin-bitwig/host"
    tools: str = "tools"


@dataclass(frozen=True, slots=True)
class Config:
    """Main configuration container."""

    ports: PortsConfig = field(default_factory=PortsConfig)
    midi: MidiConfig = field(default_factory=MidiConfig)
    paths: PathsConfig = field(default_factory=PathsConfig)
    bitwig: BitwigPathsConfig = field(default_factory=BitwigPathsConfig)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Config":
        """Create Config from a dictionary (parsed TOML)."""
        # Extract sections with proper typing
        ports_data: dict[str, Any] = dict(data.get("ports", {}))
        controller_data: dict[str, Any] = (
            dict(ports_data.pop("controller", {})) if "controller" in ports_data else {}
        )
        midi_data: dict[str, Any] = data.get("midi", {})
        paths_data: dict[str, Any] = data.get("paths", {})
        bitwig_section: Any = data.get("bitwig", {})
        bitwig_data: dict[str, Any] = {}
        bitwig_table = as_str_dict(bitwig_section)
        if bitwig_table is not None:
            for k, v in bitwig_table.items():
                bitwig_data[k] = v

        return cls(
            ports=PortsConfig(
                hardware=int(ports_data.get("hardware", BRIDGE_HARDWARE_PORT)),
                native=int(ports_data.get("native", BRIDGE_NATIVE_PORT)),
                wasm=int(ports_data.get("wasm", BRIDGE_WASM_PORT)),
                controller=ControllerPortsConfig(
                    core_native=int(
                        controller_data.get("core_native", CONTROLLER_CORE_NATIVE_PORT)
                    ),
                    core_wasm=int(controller_data.get("core_wasm", CONTROLLER_CORE_WASM_PORT)),
                    bitwig_native=int(
                        controller_data.get("bitwig_native", CONTROLLER_BITWIG_NATIVE_PORT)
                    ),
                    bitwig_wasm=int(
                        controller_data.get("bitwig_wasm", CONTROLLER_BITWIG_WASM_PORT)
                    ),
                ),
            ),
            midi=MidiConfig(
                linux=str(midi_data.get("linux", "VirMIDI")),
                macos_input=str(midi_data.get("macos_input", "MIDI Studio IN")),
                macos_output=str(midi_data.get("macos_output", "MIDI Studio OUT")),
                windows=str(midi_data.get("windows", "loopMIDI")),
            ),
            paths=PathsConfig(
                bridge=str(paths_data.get("bridge", "open-control/bridge")),
                extension=str(paths_data.get("extension", "midi-studio/plugin-bitwig/host")),
                tools=str(paths_data.get("tools", "tools")),
            ),
            bitwig=BitwigPathsConfig(
                linux=str(bitwig_data["linux"]) if bitwig_data.get("linux") else None,
                macos=str(bitwig_data["macos"]) if bitwig_data.get("macos") else None,
                windows=str(bitwig_data["windows"]) if bitwig_data.get("windows") else None,
            ),
        )


def _parse_toml(path: Path) -> Result[dict[str, Any], ConfigError]:
    """Parse a TOML file, handling import and parse errors."""
    import tomllib

    try:
        content = path.read_bytes()
        data: dict[str, Any] = tomllib.loads(content.decode("utf-8"))
        return Ok(data)
    except FileNotFoundError:
        return Err(ConfigError(f"Config file not found: {path}", path=path))
    except PermissionError:
        return Err(ConfigError(f"Permission denied reading: {path}", path=path))
    except tomllib.TOMLDecodeError as e:
        return Err(ConfigError(f"Invalid TOML syntax: {e}", path=path))
    except Exception as e:
        return Err(ConfigError(f"Error reading config: {e}", path=path))


def load_config(path: Path) -> Result[Config, ConfigError]:
    """Load and parse configuration from a TOML file.

    Args:
        path: Path to config.toml file

    Returns:
        Ok(Config) on success, Err(ConfigError) on failure
    """
    result = _parse_toml(path)
    if isinstance(result, Err):
        return result

    try:
        config = Config.from_dict(result.value)
        return Ok(config)
    except (KeyError, TypeError, ValueError) as e:
        return Err(ConfigError(f"Invalid config structure: {e}", path=path))


def load_config_or_default(path: Path) -> Config:
    """Load config from file, or return default config if file doesn't exist.

    This is useful when config is optional.
    """
    result = load_config(path)
    if isinstance(result, Ok):
        return result.value
    return Config()
