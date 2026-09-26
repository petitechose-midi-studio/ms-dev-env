"""Tests for tools/base.py - ToolSpec and Tool ABC."""

from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from ms.core.result import Ok, Result
from ms.platform.detection import Arch, Platform
from ms.tools.base import Tool, ToolSpec
from ms.tools.http import HttpClient, HttpError, MockHttpClient

# =============================================================================
# ToolSpec tests
# =============================================================================


class TestToolSpec:
    """Tests for ToolSpec dataclass."""

    def test_create_minimal(self) -> None:
        """Create ToolSpec with minimal args."""
        spec = ToolSpec(
            id="ninja",
            name="Ninja",
        )
        assert spec.id == "ninja"
        assert spec.name == "Ninja"
        assert spec.version_args == ("--version",)

    def test_create_with_version_args(self) -> None:
        """Create ToolSpec with custom version_args."""
        spec = ToolSpec(
            id="java",
            name="Java",
            version_args=("-version",),
        )
        assert spec.version_args == ("-version",)

    def test_is_frozen(self) -> None:
        """ToolSpec is immutable."""
        spec = ToolSpec(
            id="ninja",
            name="Ninja",
        )
        with pytest.raises(FrozenInstanceError):
            spec.id = "other"  # type: ignore[misc]

    def test_is_hashable(self) -> None:
        """ToolSpec can be used in sets and as dict keys."""
        spec1 = ToolSpec(id="ninja", name="Ninja")
        spec2 = ToolSpec(id="ninja", name="Ninja")
        spec3 = ToolSpec(id="cmake", name="CMake")

        # Same specs are equal and hash the same
        assert spec1 == spec2
        assert hash(spec1) == hash(spec2)

        # Different specs are not equal
        assert spec1 != spec3

        # Can use in set
        specs = {spec1, spec2, spec3}
        assert len(specs) == 2

    def test_validation_empty_id(self) -> None:
        """Reject empty id."""
        with pytest.raises(ValueError, match="id cannot be empty"):
            ToolSpec(id="", name="Ninja")

    def test_validation_empty_name(self) -> None:
        """Reject empty name."""
        with pytest.raises(ValueError, match="name cannot be empty"):
            ToolSpec(id="ninja", name="")

    def test_validation_uppercase_id(self) -> None:
        """Reject uppercase in id."""
        with pytest.raises(ValueError, match="lowercase identifier"):
            ToolSpec(id="Ninja", name="Ninja")

    def test_validation_invalid_id_chars(self) -> None:
        """Reject invalid characters in id."""
        with pytest.raises(ValueError, match="lowercase identifier"):
            ToolSpec(id="my-tool", name="My Tool")

    def test_validation_id_with_numbers(self) -> None:
        """Allow numbers in id (but not at start)."""
        spec = ToolSpec(id="sdl2", name="SDL2")
        assert spec.id == "sdl2"

    def test_validation_id_starting_with_number(self) -> None:
        """Reject id starting with number."""
        with pytest.raises(ValueError, match="lowercase identifier"):
            ToolSpec(id="2sdl", name="SDL2")


# =============================================================================
# Tool ABC tests - using concrete implementation
# =============================================================================


class ConcreteTool(Tool):
    """Concrete implementation of Tool ABC for testing."""

    spec = ToolSpec(id="testtool", name="Test Tool")

    def latest_version(self, http: HttpClient) -> Result[str, HttpError]:
        return Ok("1.0.0")

    def download_url(self, version: str, platform: Platform, arch: Arch) -> str:
        return f"https://example.com/{self.spec.id}/v{version}/{platform}-{arch}.zip"


class TestToolABC:
    """Tests for Tool abstract base class."""

    def test_spec_accessible(self) -> None:
        """Tool.spec returns the spec."""
        tool = ConcreteTool()
        assert tool.spec.id == "testtool"
        assert tool.spec.name == "Test Tool"

    def test_latest_version(self) -> None:
        """Tool.latest_version works."""
        tool = ConcreteTool()
        result = tool.latest_version(MockHttpClient())
        assert isinstance(result, Ok)
        assert result.value == "1.0.0"

    def test_download_url(self) -> None:
        """Tool.download_url returns correct URL."""
        tool = ConcreteTool()
        url = tool.download_url("1.2.0", Platform.LINUX, Arch.X64)
        assert url == "https://example.com/testtool/v1.2.0/linux-x64.zip"

    def test_install_dir_name_default(self) -> None:
        """Default install_dir_name is tool id."""
        tool = ConcreteTool()
        assert tool.install_dir_name() == "testtool"

    def test_strip_components_default(self) -> None:
        """Default strip_components is 0."""
        tool = ConcreteTool()
        assert tool.strip_components() == 0

    def test_bin_path_linux(self) -> None:
        """bin_path on Linux."""
        tool = ConcreteTool()
        path = tool.bin_path(Path("/tools"), Platform.LINUX)
        assert path == Path("/tools/testtool/testtool")

    def test_bin_path_windows(self) -> None:
        """bin_path on Windows includes .exe."""
        tool = ConcreteTool()
        path = tool.bin_path(Path("/tools"), Platform.WINDOWS)
        assert path == Path("/tools/testtool/testtool.exe")

    def test_is_installed_true(self, tmp_path: Path) -> None:
        """is_installed returns True when binary exists."""
        tool = ConcreteTool()
        binary = tmp_path / "testtool" / "testtool"
        binary.parent.mkdir(parents=True)
        binary.touch()

        assert tool.is_installed(tmp_path, Platform.LINUX) is True

    def test_is_installed_false(self, tmp_path: Path) -> None:
        """is_installed returns False when binary doesn't exist."""
        tool = ConcreteTool()
        assert tool.is_installed(tmp_path, Platform.LINUX) is False

    def test_post_install_default(self, tmp_path: Path) -> None:
        """Default post_install does nothing."""
        tool = ConcreteTool()
        # Should not raise
        tool.post_install(tmp_path, Platform.LINUX)


# =============================================================================
# Platform.exe_name() tests
# =============================================================================


class TestPlatformExeName:
    """Tests for Platform.exe_name() method."""

    def test_linux(self) -> None:
        """Linux executables have no suffix."""
        assert Platform.LINUX.exe_name("ninja") == "ninja"
        assert Platform.LINUX.exe_name("cmake") == "cmake"

    def test_macos(self) -> None:
        """macOS executables have no suffix."""
        assert Platform.MACOS.exe_name("ninja") == "ninja"
        assert Platform.MACOS.exe_name("cmake") == "cmake"

    def test_windows(self) -> None:
        """Windows executables have .exe suffix."""
        assert Platform.WINDOWS.exe_name("ninja") == "ninja.exe"
        assert Platform.WINDOWS.exe_name("cmake") == "cmake.exe"

    def test_empty_name(self) -> None:
        """Empty name returns just suffix on Windows."""
        assert Platform.LINUX.exe_name("") == ""
        assert Platform.WINDOWS.exe_name("") == ".exe"
