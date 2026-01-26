"""Phase 2 integration tests - Tools system.

This test verifies the complete tools system works together:
- Tool definitions and registry
- Version resolution (mocked HTTP)
- Download URLs
- Installation status checking
- Wrapper generation
- Shell activation scripts
"""

from pathlib import Path
from unittest.mock import patch

import pytest

from ms.platform.detection import Arch, Platform
from ms.platform.shell import generate_activation_scripts
from ms.tools.definitions import ALL_TOOLS, get_tool, get_tools_by_mode
from ms.tools.http import MockHttpClient
from ms.tools.registry import ToolRegistry
from ms.tools.state import get_installed_version, set_installed_version
from ms.tools.wrapper import WrapperGenerator, WrapperSpec


class TestToolDefinitionsIntegration:
    """Integration tests for tool definitions."""

    def test_all_tools_have_required_methods(self) -> None:
        """All tools implement the required Tool interface."""
        for tool in ALL_TOOLS:
            # Check spec
            assert tool.spec.id
            assert tool.spec.name
            assert isinstance(tool.spec.required_for, frozenset)

            # Check methods exist (don't call - may need HTTP)
            assert hasattr(tool, "latest_version")
            assert hasattr(tool, "download_url")
            assert hasattr(tool, "bin_path")
            assert hasattr(tool, "is_installed")
            assert hasattr(tool, "post_install")

    def test_github_tools_have_repos(self) -> None:
        """GitHub-based tools have repo attribute."""
        github_tools = ["ninja", "cmake", "bun", "sdl2"]
        for tool_id in github_tools:
            tool = get_tool(tool_id)
            assert tool is not None
            assert hasattr(tool, "repo")

    def test_mode_filtering_works(self) -> None:
        """Tools can be filtered by mode."""
        dev_tools = get_tools_by_mode("dev")
        enduser_tools = get_tools_by_mode("enduser")

        # Dev should have more tools than enduser
        assert len(dev_tools) >= len(enduser_tools)

        # JDK and Maven should be in both
        dev_ids = {t.spec.id for t in dev_tools}
        enduser_ids = {t.spec.id for t in enduser_tools}
        assert "jdk" in dev_ids
        assert "jdk" in enduser_ids
        assert "maven" in dev_ids
        assert "maven" in enduser_ids


class TestToolRegistryIntegration:
    """Integration tests for ToolRegistry."""

    @pytest.fixture
    def registry(self, tmp_path: Path) -> ToolRegistry:
        """Create a registry with temp tools dir."""
        return ToolRegistry(
            tools_dir=tmp_path,
            platform=Platform.LINUX,
            arch=Arch.X64,
        )

    def test_registry_lists_all_tools(self, registry: ToolRegistry) -> None:
        """Registry returns all tools."""
        tools = registry.all_tools()
        assert len(tools) == 11  # Including Zig

    def test_registry_tracks_installation_status(
        self, registry: ToolRegistry, tmp_path: Path
    ) -> None:
        """Registry correctly tracks installation status."""
        # Initially not installed
        assert not registry.is_installed("ninja")

        # Create ninja binary
        ninja_dir = tmp_path / "ninja"
        ninja_dir.mkdir()
        (ninja_dir / "ninja").touch()

        # Now installed
        assert registry.is_installed("ninja")

    def test_registry_generates_env_vars(self, registry: ToolRegistry, tmp_path: Path) -> None:
        """Registry generates correct env vars for installed tools."""
        # Install JDK
        jdk_bin = tmp_path / "jdk" / "bin"
        jdk_bin.mkdir(parents=True)
        (jdk_bin / "java").touch()

        env = registry.get_env_vars()
        assert "JAVA_HOME" in env

    def test_registry_generates_path_additions(
        self, registry: ToolRegistry, tmp_path: Path
    ) -> None:
        """Registry generates correct PATH additions."""
        # Install ninja
        ninja_dir = tmp_path / "ninja"
        ninja_dir.mkdir()
        (ninja_dir / "ninja").touch()

        paths = registry.get_path_additions()
        assert len(paths) >= 1
        assert ninja_dir in paths


class TestVersionResolutionIntegration:
    """Integration tests for version resolution (mocked HTTP)."""

    def test_ninja_version_resolution(self) -> None:
        """Ninja version resolution works with mocked HTTP."""
        client = MockHttpClient()
        client.set_json(
            "https://api.github.com/repos/ninja-build/ninja/releases/latest",
            {"tag_name": "v1.12.1"},
        )

        tool = get_tool("ninja")
        assert tool is not None

        from ms.core.result import Ok

        result = tool.latest_version(client)
        assert isinstance(result, Ok)
        assert result.value == "1.12.1"

    def test_cmake_version_resolution(self) -> None:
        """CMake version resolution works with mocked HTTP."""
        client = MockHttpClient()
        client.set_json(
            "https://api.github.com/repos/Kitware/CMake/releases/latest",
            {"tag_name": "v3.28.0"},
        )

        tool = get_tool("cmake")
        assert tool is not None

        from ms.core.result import Ok

        result = tool.latest_version(client)
        assert isinstance(result, Ok)
        assert result.value == "3.28.0"


class TestStateManagementIntegration:
    """Integration tests for version state management."""

    def test_version_tracking_roundtrip(self, tmp_path: Path) -> None:
        """Versions can be saved and loaded."""
        # Set version
        set_installed_version(tmp_path, "ninja", "1.12.1")

        # Get version
        version = get_installed_version(tmp_path, "ninja")
        assert version == "1.12.1"

    def test_version_tracking_multiple_tools(self, tmp_path: Path) -> None:
        """Multiple tools can be tracked."""
        set_installed_version(tmp_path, "ninja", "1.12.1")
        set_installed_version(tmp_path, "cmake", "3.28.0")

        assert get_installed_version(tmp_path, "ninja") == "1.12.1"
        assert get_installed_version(tmp_path, "cmake") == "3.28.0"

    def test_unknown_tool_returns_none(self, tmp_path: Path) -> None:
        """Unknown tool returns None."""
        version = get_installed_version(tmp_path, "unknown")
        assert version is None


class TestWrapperGenerationIntegration:
    """Integration tests for wrapper generation."""

    def test_wrapper_with_env_vars(self, tmp_path: Path) -> None:
        """Wrapper can set environment variables."""
        bin_dir = tmp_path / "bin"
        generator = WrapperGenerator(bin_dir)

        spec = WrapperSpec(
            name="test",
            target=Path("/tools/test"),
            env={"FOO": "bar"},
        )

        path = generator.generate(spec, Platform.LINUX)
        content = path.read_text()

        assert 'export FOO="bar"' in content


class TestShellActivationIntegration:
    """Integration tests for shell activation scripts."""

    def test_full_activation_workflow(self, tmp_path: Path) -> None:
        """Complete activation workflow works."""
        env_vars = {
            "JAVA_HOME": str(tmp_path / "jdk"),
            "M2_HOME": str(tmp_path / "maven"),
        }
        path_additions = [
            tmp_path / "ninja",
            tmp_path / "cmake" / "bin",
        ]

        scripts = generate_activation_scripts(tmp_path, env_vars, path_additions, Platform.LINUX)

        # Bash script exists
        assert "bash" in scripts
        assert scripts["bash"].exists()

        # Content is valid
        content = scripts["bash"].read_text()
        assert "JAVA_HOME" in content
        assert "PATH" in content
        assert "ms_deactivate" in content

    def test_windows_scripts_generation(self, tmp_path: Path) -> None:
        """Windows activation scripts are generated."""
        scripts = generate_activation_scripts(tmp_path, {"FOO": "bar"}, [], Platform.WINDOWS)

        assert "bash" in scripts
        assert "powershell" in scripts
        assert "cmd" in scripts

        # PowerShell has correct format
        ps_content = scripts["powershell"].read_text()
        assert "$env:FOO" in ps_content

        # Cmd has correct format
        cmd_content = scripts["cmd"].read_text()
        assert 'set "FOO=bar"' in cmd_content


class TestEndToEndWorkflow:
    """End-to-end workflow tests."""

    def test_complete_tool_setup_workflow(self, tmp_path: Path) -> None:
        """Complete workflow: registry -> status -> activation."""
        # Mock cargo to not be found (for predictable test)
        with patch("shutil.which", return_value=None):
            # 1. Create registry
            registry = ToolRegistry(
                tools_dir=tmp_path,
                platform=Platform.LINUX,
                arch=Arch.X64,
            )

            # 2. Check initial status - nothing installed
            installed = registry.get_installed_tools()
            assert len(installed) == 0

            # 3. "Install" some tools (simulate by creating binaries)
            ninja_dir = tmp_path / "ninja"
            ninja_dir.mkdir()
            (ninja_dir / "ninja").touch()

            cmake_dir = tmp_path / "cmake" / "bin"
            cmake_dir.mkdir(parents=True)
            (cmake_dir / "cmake").touch()

            # 4. Track versions
            set_installed_version(tmp_path, "ninja", "1.12.1")
            set_installed_version(tmp_path, "cmake", "3.28.0")

            # 5. Check status again
            status = registry.get_status("ninja")
            assert status.installed
            assert status.version == "1.12.1"

            # 6. Get env vars and paths
            env_vars = registry.get_env_vars()
            path_additions = registry.get_path_additions()

            # 7. Generate activation scripts
            scripts = generate_activation_scripts(
                tmp_path, env_vars, path_additions, Platform.LINUX
            )

            assert scripts["bash"].exists()
            content = scripts["bash"].read_text()
            assert "ninja" in content or "cmake" in content
