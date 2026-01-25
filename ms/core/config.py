"""Typed configuration loading and access.

This module provides dataclasses for the config.toml structure with
full type safety and validation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .result import Err, Ok, Result

__all__ = [
    "Config",
    "PortsConfig",
    "ControllerPortsConfig",
    "MidiConfig",
    "PathsConfig",
    "ConfigError",
    "load_config",
]


@dataclass(frozen=True, slots=True)
class ConfigError:
    """Error when config cannot be loaded or parsed."""

    message: str
    path: Path | None = None


@dataclass(frozen=True, slots=True)
class ControllerPortsConfig:
    """Controller port configuration."""

    core_native: int = 8000
    core_wasm: int = 8100
    bitwig_native: int = 8001
    bitwig_wasm: int = 8101


@dataclass(frozen=True, slots=True)
class PortsConfig:
    """Port configuration for bridge communication."""

    hardware: int = 9000
    native: int = 9001
    wasm: int = 9002
    controller: ControllerPortsConfig = field(default_factory=ControllerPortsConfig)


@dataclass(frozen=True, slots=True)
class MidiConfig:
    """MIDI device name configuration per platform."""

    linux: str = "VirMIDI"
    macos_input: str = "MIDI Studio IN"
    macos_output: str = "MIDI Studio OUT"
    windows: str = "loopMIDI"


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

        return cls(
            ports=PortsConfig(
                hardware=int(ports_data.get("hardware", 9000)),
                native=int(ports_data.get("native", 9001)),
                wasm=int(ports_data.get("wasm", 9002)),
                controller=ControllerPortsConfig(
                    core_native=int(controller_data.get("core_native", 8000)),
                    core_wasm=int(controller_data.get("core_wasm", 8100)),
                    bitwig_native=int(controller_data.get("bitwig_native", 8001)),
                    bitwig_wasm=int(controller_data.get("bitwig_wasm", 8101)),
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
