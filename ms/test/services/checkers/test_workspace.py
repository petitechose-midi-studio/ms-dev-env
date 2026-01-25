# SPDX-License-Identifier: MIT
"""Tests for WorkspaceChecker."""

from pathlib import Path

import pytest

from ms.core.config import Config
from ms.core.workspace import Workspace
from ms.platform.detection import Platform
from ms.services.checkers.base import CheckStatus
from ms.services.checkers.workspace import WorkspaceChecker


@pytest.fixture
def temp_workspace(tmp_path: Path) -> Workspace:
    """Create a temporary workspace."""
    return Workspace(root=tmp_path)


class TestWorkspaceChecker:
    """Tests for WorkspaceChecker."""

    def test_check_open_control_missing(self, temp_workspace: Workspace) -> None:
        checker = WorkspaceChecker(
            workspace=temp_workspace,
            platform=Platform.LINUX,
        )
        result = checker.check_open_control()
        assert result.status == CheckStatus.ERROR
        assert result.name == "open-control"
        assert "missing" in result.message

    def test_check_open_control_present(self, temp_workspace: Workspace) -> None:
        (temp_workspace.root / "open-control").mkdir()
        checker = WorkspaceChecker(
            workspace=temp_workspace,
            platform=Platform.LINUX,
        )
        result = checker.check_open_control()
        assert result.status == CheckStatus.OK
        assert result.message == "ok"

    def test_check_midi_studio_missing(self, temp_workspace: Workspace) -> None:
        checker = WorkspaceChecker(
            workspace=temp_workspace,
            platform=Platform.LINUX,
        )
        result = checker.check_midi_studio()
        assert result.status == CheckStatus.ERROR
        assert "missing" in result.message

    def test_check_midi_studio_present(self, temp_workspace: Workspace) -> None:
        (temp_workspace.root / "midi-studio").mkdir()
        checker = WorkspaceChecker(
            workspace=temp_workspace,
            platform=Platform.LINUX,
        )
        result = checker.check_midi_studio()
        assert result.status == CheckStatus.OK

    def test_check_config_missing(self, temp_workspace: Workspace) -> None:
        checker = WorkspaceChecker(
            workspace=temp_workspace,
            platform=Platform.LINUX,
        )
        result = checker.check_config()
        assert result.status == CheckStatus.WARNING
        assert "missing" in result.message

    def test_check_config_present_with_config(self, temp_workspace: Workspace) -> None:
        (temp_workspace.root / "config.toml").write_text("")
        config = Config()  # Default config
        checker = WorkspaceChecker(
            workspace=temp_workspace,
            platform=Platform.LINUX,
            config=config,
        )
        result = checker.check_config()
        assert result.status == CheckStatus.OK

    def test_check_emsdk_missing(self, temp_workspace: Workspace) -> None:
        (temp_workspace.root / "tools").mkdir()
        checker = WorkspaceChecker(
            workspace=temp_workspace,
            platform=Platform.LINUX,
        )
        result = checker.check_emsdk()
        assert result.status == CheckStatus.ERROR
        assert "missing" in result.message

    def test_check_emsdk_present(self, temp_workspace: Workspace) -> None:
        emsdk_dir = temp_workspace.root / "tools" / "emsdk"
        emsdk_dir.mkdir(parents=True)
        (emsdk_dir / "emsdk.py").write_text("")
        checker = WorkspaceChecker(
            workspace=temp_workspace,
            platform=Platform.LINUX,
        )
        result = checker.check_emsdk()
        assert result.status == CheckStatus.OK

    def test_check_bridge_not_built(self, temp_workspace: Workspace) -> None:
        checker = WorkspaceChecker(
            workspace=temp_workspace,
            platform=Platform.LINUX,
        )
        result = checker.check_bridge()
        assert result.status == CheckStatus.WARNING
        assert "not built" in result.message

    def test_check_bridge_built(self, temp_workspace: Workspace) -> None:
        bridge_bin = temp_workspace.root / "open-control" / "bridge" / "target" / "release"
        bridge_bin.mkdir(parents=True)
        (bridge_bin / "oc-bridge").write_text("")
        checker = WorkspaceChecker(
            workspace=temp_workspace,
            platform=Platform.LINUX,
        )
        result = checker.check_bridge()
        assert result.status == CheckStatus.OK
        assert "built" in result.message

    def test_check_bridge_built_windows(self, temp_workspace: Workspace) -> None:
        bridge_bin = temp_workspace.root / "open-control" / "bridge" / "target" / "release"
        bridge_bin.mkdir(parents=True)
        (bridge_bin / "oc-bridge.exe").write_text("")
        checker = WorkspaceChecker(
            workspace=temp_workspace,
            platform=Platform.WINDOWS,
        )
        result = checker.check_bridge()
        assert result.status == CheckStatus.OK

    def test_check_bitwig_host_missing(self, temp_workspace: Workspace) -> None:
        checker = WorkspaceChecker(
            workspace=temp_workspace,
            platform=Platform.LINUX,
        )
        result = checker.check_bitwig_host()
        assert result.status == CheckStatus.ERROR

    def test_check_bitwig_host_present(self, temp_workspace: Workspace) -> None:
        host_dir = temp_workspace.root / "midi-studio" / "plugin-bitwig" / "host"
        host_dir.mkdir(parents=True)
        (host_dir / "pom.xml").write_text("")
        checker = WorkspaceChecker(
            workspace=temp_workspace,
            platform=Platform.LINUX,
        )
        result = checker.check_bitwig_host()
        assert result.status == CheckStatus.OK

    def test_check_all_returns_all_results(self, temp_workspace: Workspace) -> None:
        checker = WorkspaceChecker(
            workspace=temp_workspace,
            platform=Platform.LINUX,
        )
        results = checker.check_all()
        # Should have results for all checks
        names = [r.name for r in results]
        assert "open-control" in names
        assert "midi-studio" in names
        assert "config.toml" in names
        assert "emsdk" in names
        assert "oc-bridge" in names
        assert "bitwig host" in names
        assert "bitwig extensions" in names

    def test_uses_config_paths(self, temp_workspace: Workspace) -> None:
        """Test that checker uses paths from config."""
        from ms.core.config import Config, PathsConfig

        config = Config(
            paths=PathsConfig(
                bridge="custom/bridge",
                extension="custom/ext",
                tools="custom/tools",
            )
        )
        # Create custom paths
        emsdk_dir = temp_workspace.root / "custom" / "tools" / "emsdk"
        emsdk_dir.mkdir(parents=True)
        (emsdk_dir / "emsdk.py").write_text("")

        checker = WorkspaceChecker(
            workspace=temp_workspace,
            platform=Platform.LINUX,
            config=config,
        )
        result = checker.check_emsdk()
        assert result.status == CheckStatus.OK
