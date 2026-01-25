"""Tests for ms.core.config module."""

from __future__ import annotations

from pathlib import Path

import pytest

from ms.core.config import (
    Config,
    ConfigError,
    ControllerPortsConfig,
    MidiConfig,
    PathsConfig,
    PortsConfig,
    load_config,
    load_config_or_default,
)
from ms.core.result import Err, Ok


class TestControllerPortsConfig:
    """Test ControllerPortsConfig defaults and structure."""

    def test_defaults(self) -> None:
        config = ControllerPortsConfig()
        assert config.core_native == 8000
        assert config.core_wasm == 8100
        assert config.bitwig_native == 8001
        assert config.bitwig_wasm == 8101

    def test_custom_values(self) -> None:
        config = ControllerPortsConfig(
            core_native=1000,
            core_wasm=1100,
            bitwig_native=1001,
            bitwig_wasm=1101,
        )
        assert config.core_native == 1000
        assert config.core_wasm == 1100

    def test_frozen(self) -> None:
        config = ControllerPortsConfig()
        with pytest.raises(AttributeError):
            config.core_native = 9999  # type: ignore[misc]


class TestPortsConfig:
    """Test PortsConfig defaults and structure."""

    def test_defaults(self) -> None:
        config = PortsConfig()
        assert config.hardware == 9000
        assert config.native == 9001
        assert config.wasm == 9002
        assert isinstance(config.controller, ControllerPortsConfig)

    def test_nested_controller(self) -> None:
        config = PortsConfig()
        assert config.controller.core_native == 8000


class TestMidiConfig:
    """Test MidiConfig defaults."""

    def test_defaults(self) -> None:
        config = MidiConfig()
        assert config.linux == "VirMIDI"
        assert config.macos_input == "MIDI Studio IN"
        assert config.macos_output == "MIDI Studio OUT"
        assert config.windows == "loopMIDI"


class TestPathsConfig:
    """Test PathsConfig defaults."""

    def test_defaults(self) -> None:
        config = PathsConfig()
        assert config.bridge == "open-control/bridge"
        assert config.extension == "midi-studio/plugin-bitwig/host"
        assert config.tools == "tools"


class TestConfig:
    """Test main Config class."""

    def test_defaults(self) -> None:
        config = Config()
        assert isinstance(config.ports, PortsConfig)
        assert isinstance(config.midi, MidiConfig)
        assert isinstance(config.paths, PathsConfig)

    def test_from_dict_empty(self) -> None:
        config = Config.from_dict({})
        # Should use all defaults
        assert config.ports.hardware == 9000
        assert config.midi.linux == "VirMIDI"

    def test_from_dict_partial(self) -> None:
        data = {
            "ports": {"hardware": 1234},
            "midi": {"linux": "CustomMIDI"},
        }
        config = Config.from_dict(data)
        assert config.ports.hardware == 1234
        assert config.ports.native == 9001  # default
        assert config.midi.linux == "CustomMIDI"
        assert config.midi.windows == "loopMIDI"  # default

    def test_from_dict_full(self) -> None:
        data = {
            "ports": {
                "hardware": 1000,
                "native": 1001,
                "wasm": 1002,
                "controller": {
                    "core_native": 2000,
                    "core_wasm": 2100,
                    "bitwig_native": 2001,
                    "bitwig_wasm": 2101,
                },
            },
            "midi": {
                "linux": "Lin",
                "macos_input": "MacIn",
                "macos_output": "MacOut",
                "windows": "Win",
            },
            "paths": {
                "bridge": "custom/bridge",
                "extension": "custom/ext",
                "tools": "custom/tools",
            },
        }
        config = Config.from_dict(data)
        assert config.ports.hardware == 1000
        assert config.ports.controller.core_native == 2000
        assert config.midi.linux == "Lin"
        assert config.paths.bridge == "custom/bridge"


class TestLoadConfig:
    """Test load_config function."""

    def test_load_valid_config(self, tmp_path: Path) -> None:
        config_file = tmp_path / "config.toml"
        config_file.write_text("""
[ports]
hardware = 5000
native = 5001
wasm = 5002

[ports.controller]
core_native = 6000

[midi]
linux = "TestMIDI"

[paths]
bridge = "test/bridge"
""")
        result = load_config(config_file)
        assert isinstance(result, Ok)
        config = result.value
        assert config.ports.hardware == 5000
        assert config.ports.controller.core_native == 6000
        assert config.midi.linux == "TestMIDI"
        assert config.paths.bridge == "test/bridge"

    def test_load_empty_config(self, tmp_path: Path) -> None:
        config_file = tmp_path / "config.toml"
        config_file.write_text("")
        result = load_config(config_file)
        assert isinstance(result, Ok)
        # Should use all defaults
        assert result.value.ports.hardware == 9000

    def test_load_missing_file(self, tmp_path: Path) -> None:
        result = load_config(tmp_path / "missing.toml")
        assert isinstance(result, Err)
        assert "not found" in result.error.message

    def test_load_invalid_toml(self, tmp_path: Path) -> None:
        config_file = tmp_path / "config.toml"
        config_file.write_text("this is not valid toml [[[")
        result = load_config(config_file)
        assert isinstance(result, Err)
        assert "TOML" in result.error.message or "syntax" in result.error.message.lower()

    def test_load_with_comments(self, tmp_path: Path) -> None:
        config_file = tmp_path / "config.toml"
        config_file.write_text("""
# This is a comment
[ports]
# Another comment
hardware = 7777  # inline comment
""")
        result = load_config(config_file)
        assert isinstance(result, Ok)
        assert result.value.ports.hardware == 7777


class TestLoadConfigOrDefault:
    """Test load_config_or_default convenience function."""

    def test_returns_config_when_file_exists(self, tmp_path: Path) -> None:
        config_file = tmp_path / "config.toml"
        config_file.write_text("[ports]\nhardware = 4444\n")
        config = load_config_or_default(config_file)
        assert config.ports.hardware == 4444

    def test_returns_default_when_missing(self, tmp_path: Path) -> None:
        config = load_config_or_default(tmp_path / "missing.toml")
        assert config.ports.hardware == 9000  # default

    def test_returns_default_on_invalid(self, tmp_path: Path) -> None:
        config_file = tmp_path / "config.toml"
        config_file.write_text("invalid[[[")
        config = load_config_or_default(config_file)
        assert config.ports.hardware == 9000  # default


class TestConfigError:
    """Test ConfigError dataclass."""

    def test_create(self) -> None:
        err = ConfigError(message="test error")
        assert err.message == "test error"
        assert err.path is None

    def test_create_with_path(self, tmp_path: Path) -> None:
        err = ConfigError(message="test", path=tmp_path / "config.toml")
        assert err.path is not None


class TestRealConfig:
    """Test with real workspace config if available."""

    def test_load_real_config(self) -> None:
        """Load the real workspace config.toml if it exists."""
        # This assumes tests run from workspace root
        config_path = Path("config.toml")
        if config_path.exists():
            result = load_config(config_path)
            assert isinstance(result, Ok)
            config = result.value
            # Verify it matches expected structure
            assert config.ports.hardware == 9000
            assert config.midi.linux == "VirMIDI"
