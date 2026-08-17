"""Tests for ToolRegistry."""

from pathlib import Path

import pytest

from ms.platform.detection import Platform
from ms.tools.base import Mode
from ms.tools.registry import ToolRegistry


@pytest.fixture
def registry(tmp_path: Path) -> ToolRegistry:
    """Create a registry with temp tools dir."""
    return ToolRegistry(
        tools_dir=tmp_path,
        platform=Platform.LINUX,
    )


class TestToolRegistry:
    """Tests for ToolRegistry initialization."""

    def test_init(self, tmp_path: Path) -> None:
        """Registry initializes with correct attributes."""
        registry = ToolRegistry(
            tools_dir=tmp_path,
            platform=Platform.LINUX,
        )

        assert registry.tools_dir == tmp_path

    def test_properties(self, registry: ToolRegistry) -> None:
        """Registry properties are accessible."""
        assert registry.tools_dir is not None


class TestToolRegistryGetTool:
    """Tests for ToolRegistry.get_tool()."""

    def test_get_existing_tool(self, registry: ToolRegistry) -> None:
        """get_tool returns tool for valid ID."""
        tool = registry.get_tool("ninja")

        assert tool is not None
        assert tool.spec.id == "ninja"

    def test_get_nonexistent_tool(self, registry: ToolRegistry) -> None:
        """get_tool returns None for invalid ID."""
        tool = registry.get_tool("nonexistent")

        assert tool is None


class TestToolRegistryToolsForMode:
    """Tests for ToolRegistry.tools_for_mode()."""

    def test_dev_mode_with_enum(self, registry: ToolRegistry) -> None:
        """tools_for_mode works with Mode enum."""
        tools = registry.tools_for_mode(Mode.DEV)

        assert len(tools) > 0
        for tool in tools:
            assert tool.spec.is_required_for(Mode.DEV)

    def test_dev_mode_with_string(self, registry: ToolRegistry) -> None:
        """tools_for_mode works with string."""
        tools = registry.tools_for_mode("dev")

        assert len(tools) > 0

    def test_enduser_mode(self, registry: ToolRegistry) -> None:
        """tools_for_mode returns enduser tools."""
        tools = registry.tools_for_mode(Mode.ENDUSER)

        for tool in tools:
            assert tool.spec.is_required_for(Mode.ENDUSER)


class TestToolRegistryIsInstalled:
    """Tests for ToolRegistry.is_installed()."""

    def test_not_installed_by_default(self, registry: ToolRegistry) -> None:
        """Tools are not installed by default."""
        assert registry.is_installed("ninja") is False

    def test_installed_when_binary_exists(self, registry: ToolRegistry) -> None:
        """Tool is installed when binary exists."""
        # Create ninja binary
        ninja_dir = registry.tools_dir / "ninja"
        ninja_dir.mkdir()
        (ninja_dir / "ninja").touch()

        assert registry.is_installed("ninja") is True

    def test_accepts_tool_instance(self, registry: ToolRegistry) -> None:
        """is_installed accepts Tool instance."""
        tool = registry.get_tool("ninja")
        assert tool is not None

        assert registry.is_installed(tool) is False

    def test_unknown_tool_returns_false(self, registry: ToolRegistry) -> None:
        """is_installed returns False for unknown tool ID."""
        assert registry.is_installed("nonexistent") is False


class TestToolRegistryGetBinPath:
    """Tests for ToolRegistry.get_bin_path()."""

    def test_returns_none_if_not_installed(self, registry: ToolRegistry) -> None:
        """get_bin_path returns None if not installed."""
        path = registry.get_bin_path("ninja")

        assert path is None

    def test_returns_path_if_installed(self, registry: ToolRegistry) -> None:
        """get_bin_path returns path if installed."""
        # Create ninja binary
        ninja_dir = registry.tools_dir / "ninja"
        ninja_dir.mkdir()
        (ninja_dir / "ninja").touch()

        path = registry.get_bin_path("ninja")

        assert path is not None
        assert path.name == "ninja"

    def test_unknown_tool_returns_none(self, registry: ToolRegistry) -> None:
        """get_bin_path returns None for unknown tool."""
        path = registry.get_bin_path("nonexistent")

        assert path is None


class TestToolRegistryGetEnvVars:
    """Tests for ToolRegistry.get_env_vars()."""

    def test_empty_when_nothing_installed(self, registry: ToolRegistry) -> None:
        """get_env_vars returns empty dict when nothing installed."""
        env = registry.get_env_vars()

        assert env == {}

    def test_java_home_when_jdk_installed(self, registry: ToolRegistry) -> None:
        """JAVA_HOME is set when JDK is installed."""
        # Create JDK structure
        jdk_bin = registry.tools_dir / "jdk" / "bin"
        jdk_bin.mkdir(parents=True)
        (jdk_bin / "java").touch()

        env = registry.get_env_vars()

        assert "JAVA_HOME" in env
        assert "jdk" in env["JAVA_HOME"]

    def test_m2_home_when_maven_installed(self, registry: ToolRegistry) -> None:
        """M2_HOME is set when Maven is installed."""
        # Create Maven structure
        maven_bin = registry.tools_dir / "maven" / "bin"
        maven_bin.mkdir(parents=True)
        (maven_bin / "mvn").touch()

        env = registry.get_env_vars()

        assert "M2_HOME" in env
        assert "maven" in env["M2_HOME"]


class TestToolRegistryGetPathAdditions:
    """Tests for ToolRegistry.get_path_additions()."""

    def test_empty_when_nothing_installed(self, registry: ToolRegistry) -> None:
        """get_path_additions returns empty list when nothing installed."""
        paths = registry.get_path_additions()

        assert paths == []

    def test_includes_installed_tool_dirs(self, registry: ToolRegistry) -> None:
        """Installed tool directories are included."""
        # Create ninja binary
        ninja_dir = registry.tools_dir / "ninja"
        ninja_dir.mkdir()
        (ninja_dir / "ninja").touch()

        paths = registry.get_path_additions()

        assert len(paths) >= 1
        assert ninja_dir in paths

    def test_no_duplicates(self, registry: ToolRegistry) -> None:
        """No duplicate paths."""
        # Create multiple tools
        ninja_dir = registry.tools_dir / "ninja"
        ninja_dir.mkdir()
        (ninja_dir / "ninja").touch()

        cmake_bin = registry.tools_dir / "cmake" / "bin"
        cmake_bin.mkdir(parents=True)
        (cmake_bin / "cmake").touch()

        paths = registry.get_path_additions()

        assert len(paths) == len(set(paths))
