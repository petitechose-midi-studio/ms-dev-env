"""Tests for tools.definitions module."""

from ms.tools.base import Mode
from ms.tools.definitions import (
    ALL_TOOLS,
    BunTool,
    CargoTool,
    CMakeTool,
    EmscriptenTool,
    JdkTool,
    MavenTool,
    NinjaTool,
    PlatformioTool,
    Sdl2Tool,
    UvTool,
    get_tool,
    get_tools_by_mode,
)


class TestAllTools:
    """Tests for ALL_TOOLS registry."""

    def test_all_tools_count(self) -> None:
        """ALL_TOOLS contains all 10 tools."""
        assert len(ALL_TOOLS) == 10

    def test_all_tools_unique_ids(self) -> None:
        """All tools have unique IDs."""
        ids = [tool.spec.id for tool in ALL_TOOLS]
        assert len(ids) == len(set(ids))

    def test_all_tools_have_specs(self) -> None:
        """All tools have valid specs."""
        for tool in ALL_TOOLS:
            assert tool.spec.id
            assert tool.spec.name
            assert isinstance(tool.spec.required_for, frozenset)

    def test_expected_tools_present(self) -> None:
        """Expected tools are in ALL_TOOLS."""
        ids = {tool.spec.id for tool in ALL_TOOLS}
        expected = {
            "ninja",
            "cmake",
            "bun",
            "uv",
            "jdk",
            "maven",
            "emscripten",
            "platformio",
            "cargo",
            "sdl2",
        }
        assert ids == expected


class TestGetTool:
    """Tests for get_tool function."""

    def test_get_existing_tool(self) -> None:
        """get_tool returns tool for valid ID."""
        ninja = get_tool("ninja")
        assert ninja is not None
        assert ninja.spec.id == "ninja"

    def test_get_nonexistent_tool(self) -> None:
        """get_tool returns None for invalid ID."""
        result = get_tool("nonexistent")
        assert result is None

    def test_get_all_tools_by_id(self) -> None:
        """get_tool works for all tool IDs."""
        for tool in ALL_TOOLS:
            result = get_tool(tool.spec.id)
            assert result is not None
            assert result.spec.id == tool.spec.id


class TestGetToolsByMode:
    """Tests for get_tools_by_mode function."""

    def test_dev_mode_tools(self) -> None:
        """get_tools_by_mode returns dev tools."""
        dev_tools = get_tools_by_mode("dev")
        assert len(dev_tools) > 0

        # All returned tools should be required for dev
        for tool in dev_tools:
            assert tool.spec.is_required_for(Mode.DEV)

    def test_enduser_mode_tools(self) -> None:
        """get_tools_by_mode returns enduser tools."""
        enduser_tools = get_tools_by_mode("enduser")

        # All returned tools should be required for enduser
        for tool in enduser_tools:
            assert tool.spec.is_required_for(Mode.ENDUSER)

    def test_case_insensitive(self) -> None:
        """get_tools_by_mode is case insensitive."""
        dev1 = get_tools_by_mode("dev")
        dev2 = get_tools_by_mode("DEV")
        dev3 = get_tools_by_mode("Dev")

        assert len(dev1) == len(dev2) == len(dev3)

    def test_jdk_maven_required_for_both(self) -> None:
        """JDK and Maven are required for both modes."""
        dev_tools = get_tools_by_mode("dev")
        enduser_tools = get_tools_by_mode("enduser")

        dev_ids = {tool.spec.id for tool in dev_tools}
        enduser_ids = {tool.spec.id for tool in enduser_tools}

        # JDK and Maven should be in both
        assert "jdk" in dev_ids
        assert "jdk" in enduser_ids
        assert "maven" in dev_ids
        assert "maven" in enduser_ids


class TestToolClassExports:
    """Tests for tool class exports."""

    def test_all_classes_exported(self) -> None:
        """All tool classes are exported."""
        # These should not raise
        assert NinjaTool is not None
        assert CMakeTool is not None
        assert BunTool is not None
        assert UvTool is not None
        assert JdkTool is not None
        assert MavenTool is not None
        assert EmscriptenTool is not None
        assert PlatformioTool is not None
        assert CargoTool is not None
        assert Sdl2Tool is not None

    def test_classes_can_be_instantiated(self) -> None:
        """All tool classes can be instantiated."""
        tools = [
            NinjaTool(),
            CMakeTool(),
            BunTool(),
            UvTool(),
            JdkTool(),
            MavenTool(),
            EmscriptenTool(),
            PlatformioTool(),
            CargoTool(),
            Sdl2Tool(),
        ]
        assert len(tools) == 10
