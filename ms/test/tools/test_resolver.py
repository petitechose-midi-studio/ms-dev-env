"""Tests for tools/resolver.py - Tool resolution."""

from pathlib import Path

import pytest

from ms.core.result import Err, Ok
from ms.platform.detection import Arch, Platform
from ms.tools.base import Mode, ToolSpec
from ms.tools.github import GitHubTool
from ms.tools.resolver import ResolvedTool, ToolNotFoundError, ToolResolver


# =============================================================================
# Mock tool for testing
# =============================================================================


class MockTool(GitHubTool):
    """Simple tool for testing."""

    spec = ToolSpec(id="mocktool", name="Mock Tool", required_for=frozenset({Mode.DEV}))
    repo = "test/mock"

    def asset_name(self, version: str, platform: Platform, arch: Arch) -> str:
        return "mocktool.zip"


# =============================================================================
# ToolNotFoundError tests
# =============================================================================


class TestToolNotFoundError:
    """Tests for ToolNotFoundError."""

    def test_create(self) -> None:
        """Create ToolNotFoundError."""
        error = ToolNotFoundError(tool_id="ninja", message="Not found")
        assert error.tool_id == "ninja"
        assert error.message == "Not found"

    def test_str(self) -> None:
        """String representation."""
        error = ToolNotFoundError(tool_id="cmake", message="Tool missing")
        assert "cmake" in str(error)
        assert "Tool missing" in str(error)


# =============================================================================
# ResolvedTool tests
# =============================================================================


class TestResolvedTool:
    """Tests for ResolvedTool dataclass."""

    def test_create_bundled(self) -> None:
        """Create bundled ResolvedTool."""
        resolved = ResolvedTool(
            tool_id="ninja",
            path=Path("/tools/ninja/ninja"),
            bundled=True,
        )
        assert resolved.tool_id == "ninja"
        assert resolved.path == Path("/tools/ninja/ninja")
        assert resolved.bundled is True

    def test_create_system(self) -> None:
        """Create system ResolvedTool."""
        resolved = ResolvedTool(
            tool_id="git",
            path=Path("/usr/bin/git"),
            bundled=False,
        )
        assert resolved.bundled is False


# =============================================================================
# ToolResolver tests
# =============================================================================


class TestToolResolver:
    """Tests for ToolResolver."""

    def test_resolve_bundled(self, tmp_path: Path) -> None:
        """Resolve bundled tool."""
        # Create bundled binary
        tools_dir = tmp_path / "tools"
        binary = tools_dir / "mocktool" / "mocktool"
        binary.parent.mkdir(parents=True)
        binary.touch()

        tool = MockTool()
        resolver = ToolResolver(tools_dir, Platform.LINUX)
        result = resolver.resolve(tool)

        assert isinstance(result, Ok)
        assert result.value.tool_id == "mocktool"
        assert result.value.path == binary
        assert result.value.bundled is True

    def test_resolve_bundled_windows(self, tmp_path: Path) -> None:
        """Resolve bundled tool on Windows."""
        # Create bundled binary with .exe
        tools_dir = tmp_path / "tools"
        binary = tools_dir / "mocktool" / "mocktool.exe"
        binary.parent.mkdir(parents=True)
        binary.touch()

        tool = MockTool()
        resolver = ToolResolver(tools_dir, Platform.WINDOWS)
        result = resolver.resolve(tool)

        assert isinstance(result, Ok)
        assert result.value.path == binary

    def test_resolve_not_found(self, tmp_path: Path) -> None:
        """Error when tool not found anywhere."""
        tools_dir = tmp_path / "tools"
        tools_dir.mkdir()

        tool = MockTool()
        resolver = ToolResolver(tools_dir, Platform.LINUX)
        result = resolver.resolve(tool)

        assert isinstance(result, Err)
        assert result.error.tool_id == "mocktool"


class TestToolResolverProperties:
    """Tests for ToolResolver properties."""

    def test_tools_dir(self, tmp_path: Path) -> None:
        """tools_dir property."""
        resolver = ToolResolver(tmp_path / "tools", Platform.LINUX)
        assert resolver.tools_dir == tmp_path / "tools"

    def test_platform(self, tmp_path: Path) -> None:
        """platform property."""
        resolver = ToolResolver(tmp_path, Platform.MACOS)
        assert resolver.platform == Platform.MACOS
