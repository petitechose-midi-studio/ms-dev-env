"""Typed configuration loading and access.

This module provides dataclasses for the config.toml structure with
full type safety and validation.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

from .result import Err, Ok, Result
from .structured import StrDict, as_str_dict, get_int, get_str, get_table

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
    def from_dict(cls, data: Mapping[str, object]) -> Config:
        """Create Config from a mapping (parsed TOML)."""
        ports: StrDict = get_table(data, "ports") or {}
        controller: StrDict = get_table(ports, "controller") or {}
        midi: StrDict = get_table(data, "midi") or {}
        paths: StrDict = get_table(data, "paths") or {}
        bitwig: StrDict = get_table(data, "bitwig") or {}

        return cls(
            ports=PortsConfig(
                hardware=get_int(ports, "hardware") or BRIDGE_HARDWARE_PORT,
                native=get_int(ports, "native") or BRIDGE_NATIVE_PORT,
                wasm=get_int(ports, "wasm") or BRIDGE_WASM_PORT,
                controller=ControllerPortsConfig(
                    core_native=get_int(controller, "core_native") or CONTROLLER_CORE_NATIVE_PORT,
                    core_wasm=get_int(controller, "core_wasm") or CONTROLLER_CORE_WASM_PORT,
                    bitwig_native=get_int(controller, "bitwig_native")
                    or CONTROLLER_BITWIG_NATIVE_PORT,
                    bitwig_wasm=get_int(controller, "bitwig_wasm") or CONTROLLER_BITWIG_WASM_PORT,
                ),
            ),
            midi=MidiConfig(
                linux=get_str(midi, "linux") or "VirMIDI",
                macos_input=get_str(midi, "macos_input") or "MIDI Studio IN",
                macos_output=get_str(midi, "macos_output") or "MIDI Studio OUT",
                windows=get_str(midi, "windows") or "loopMIDI",
            ),
            paths=PathsConfig(
                bridge=get_str(paths, "bridge") or "open-control/bridge",
                extension=get_str(paths, "extension") or "midi-studio/plugin-bitwig/host",
                tools=get_str(paths, "tools") or "tools",
            ),
            bitwig=BitwigPathsConfig(
                linux=get_str(bitwig, "linux"),
                macos=get_str(bitwig, "macos"),
                windows=get_str(bitwig, "windows"),
            ),
        )


def _parse_toml(path: Path) -> Result[StrDict, ConfigError]:
    """Parse a TOML file, handling import and parse errors."""
    import tomllib

    try:
        content = path.read_bytes()
        data_obj: object = tomllib.loads(content.decode("utf-8"))
        data = as_str_dict(data_obj)
        if data is None:
            return Err(ConfigError("Config root must be a TOML table", path=path))
        return Ok(data)
    except FileNotFoundError:
        return Err(ConfigError(f"Config file not found: {path}", path=path))
    except PermissionError:
        return Err(ConfigError(f"Permission denied reading: {path}", path=path))
    except tomllib.TOMLDecodeError as e:
        return Err(ConfigError(f"Invalid TOML syntax: {e}", path=path))
    except UnicodeDecodeError as e:
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
