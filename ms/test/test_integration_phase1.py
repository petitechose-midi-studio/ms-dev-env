"""Integration tests for Phase 1 modules.

This test verifies that all Phase 1 modules work together correctly.
It tests the complete flow from workspace detection to config loading
with console output.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from ms.core import (
    Config,
    Err,
    ErrorCode,
    Ok,
    Workspace,
    detect_workspace,
    load_config,
)
from ms.output import MockConsole, Style
from ms.platform import Platform, detect, is_windows


class TestPhase1Integration:
    """Integration tests combining Phase 1 modules."""

    def test_workspace_to_config_flow(self, tmp_path: Path) -> None:
        """Test detecting workspace and loading its config."""
        # Create a workspace
        (tmp_path / "commands").mkdir()
        config_content = """
[ports]
hardware = 7777

[midi]
linux = "IntegrationTest"
"""
        (tmp_path / "config.toml").write_text(config_content)

        # Create Workspace directly (bypass detect which might find real workspace)
        workspace = Workspace(root=tmp_path)

        # Load config from workspace
        config_result = load_config(workspace.config_path)
        assert isinstance(config_result, Ok)
        config = config_result.value

        # Verify config was loaded correctly
        assert config.ports.hardware == 7777
        assert config.midi.linux == "IntegrationTest"

    def test_console_reports_workspace_detection(self, tmp_path: Path) -> None:
        """Test using MockConsole to report workspace detection results."""
        console = MockConsole()

        # Simulate workspace detection with output
        (tmp_path / "commands").mkdir()
        (tmp_path / "config.toml").write_text("")

        result = detect_workspace(start_dir=tmp_path)

        if isinstance(result, Ok):
            console.success(f"Found workspace at {result.value.root}")
        else:
            console.error(f"Workspace not found: {result.error.message}")

        assert console.has_success()
        assert "workspace" in console.text.lower()

    def test_platform_aware_config(self) -> None:
        """Test that config can provide platform-specific values."""
        config = Config()
        platform_info = detect()

        # Get MIDI device name based on platform
        if platform_info.platform == Platform.LINUX:
            midi_name = config.midi.linux
            assert midi_name == "VirMIDI"
        elif platform_info.platform == Platform.WINDOWS:
            midi_name = config.midi.windows
            assert midi_name == "loopMIDI"
        elif platform_info.platform == Platform.MACOS:
            midi_name = config.midi.macos_input
            assert midi_name == "MIDI Studio IN"

    def test_error_handling_flow(self, tmp_path: Path) -> None:
        """Test complete error handling from detection to output."""
        console = MockConsole()

        # Try to detect workspace in a non-workspace directory
        isolated = tmp_path / "isolated"
        isolated.mkdir()

        result = detect_workspace(start_dir=isolated)

        # The result might be Ok (found real workspace) or Err
        if isinstance(result, Err):
            # Report error with proper error code
            error_code = ErrorCode.ENV_ERROR
            console.error(f"{result.error.message} (code: {error_code})")
            assert console.has_error()
            assert error_code.is_error

    def test_workspace_paths_with_platform(self, tmp_path: Path) -> None:
        """Test that workspace paths work with platform detection."""
        # Create workspace
        (tmp_path / "commands").mkdir()
        (tmp_path / "config.toml").write_text("")

        workspace = Workspace(root=tmp_path)
        platform_info = detect()

        # Bin path should have correct exe suffix
        bin_dir = workspace.bin_dir
        exe_suffix = platform_info.platform.exe_suffix

        expected_bridge = bin_dir / f"oc-bridge{exe_suffix}"
        assert str(expected_bridge).endswith(f"oc-bridge{exe_suffix}")

    def test_result_chaining_with_config(self, tmp_path: Path) -> None:
        """Test Result monad chaining with config operations."""
        (tmp_path / ".ms-workspace").write_text("")
        (tmp_path / "config.toml").write_text("[ports]\nhardware = 1234\n")

        # Create workspace directly and load config
        workspace = Workspace(root=tmp_path)
        config_result = load_config(workspace.config_path)

        assert isinstance(config_result, Ok)
        assert config_result.value.ports.hardware == 1234


class TestRealWorkspaceIntegration:
    """Integration tests with the real workspace (if available)."""

    def test_full_real_workspace_flow(self) -> None:
        """Test complete flow with real workspace."""
        # Detect real workspace
        result = detect_workspace()

        if isinstance(result, Ok):
            workspace = result.value

            # Verify workspace is valid
            assert workspace.exists()
            assert workspace.marker_path.exists()

            # Load real config (optional)
            if workspace.config_path.exists():
                config_result = load_config(workspace.config_path)
                assert isinstance(config_result, Ok)

                config = config_result.value

                # Verify real config values match expected
                assert config.ports.hardware == 9000
                assert config.ports.native == 9001
                assert config.ports.wasm == 9002
                assert config.midi.linux == "VirMIDI"
                assert config.paths.bridge == "open-control/bridge"

    def test_platform_specific_operation(self) -> None:
        """Test platform-specific logic with real workspace."""
        platform_info = detect()
        console = MockConsole()

        console.header(f"Platform: {platform_info}")
        console.info(f"Architecture: {platform_info.arch}")

        if platform_info.is_windows:
            console.info("Running on Windows")
        elif platform_info.is_linux:
            console.info(f"Linux distro: {platform_info.distro}")
        elif platform_info.is_macos:
            console.info("Running on macOS")

        assert len(console.outputs) >= 2


class TestModuleExports:
    """Test that all Phase 1 modules export correctly."""

    def test_core_exports(self) -> None:
        """Test ms.core exports."""
        from ms.core import (
            Config,
            ConfigError,
            Err,
            ErrorCode,
            Ok,
            Result,
            Workspace,
            WorkspaceError,
            detect_workspace,
            is_err,
            is_ok,
            load_config,
        )

        # All should be importable
        assert Config is not None
        assert ErrorCode is not None
        assert Ok is not None
        assert Err is not None
        assert Workspace is not None

    def test_platform_exports(self) -> None:
        """Test ms.platform exports."""
        from ms.platform import (
            Arch,
            LinuxDistro,
            Platform,
            PlatformInfo,
            detect,
            detect_linux_distro,
            home,
            is_linux,
            is_macos,
            is_windows,
            user_config_dir,
        )

        assert Platform is not None
        assert Arch is not None
        assert detect is not None
        assert home is not None
        assert user_config_dir is not None

    def test_output_exports(self) -> None:
        """Test ms.output exports."""
        from ms.output import (
            ConsoleProtocol,
            MockConsole,
            RichConsole,
            Style,
        )

        assert ConsoleProtocol is not None
        assert MockConsole is not None
        assert RichConsole is not None
        assert Style is not None
