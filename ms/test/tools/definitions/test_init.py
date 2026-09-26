"""Tests for tools.definitions module."""

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
)


class TestAllTools:
    """Tests for ALL_TOOLS registry."""

    def test_all_tools_count(self) -> None:
        """ALL_TOOLS contains all 11 tools."""
        assert len(ALL_TOOLS) == 11

    def test_all_tools_unique_ids(self) -> None:
        """All tools have unique IDs."""
        ids = [tool.spec.id for tool in ALL_TOOLS]
        assert len(ids) == len(set(ids))

    def test_all_tools_have_specs(self) -> None:
        """All tools have valid specs."""
        for tool in ALL_TOOLS:
            assert tool.spec.id
            assert tool.spec.name

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
            "zig",
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
