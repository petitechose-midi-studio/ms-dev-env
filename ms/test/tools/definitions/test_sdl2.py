"""Tests for Sdl2Tool."""

from pathlib import Path
from unittest.mock import patch

from ms.core.result import Ok
from ms.platform.detection import Arch, Platform
from ms.tools.base import Mode
from ms.tools.definitions.sdl2 import Sdl2Tool
from ms.tools.http import MockHttpClient


class TestSdl2Tool:
    """Tests for Sdl2Tool."""

    def test_spec(self) -> None:
        """Sdl2Tool has correct spec."""
        tool = Sdl2Tool()

        assert tool.spec.id == "sdl2"
        assert tool.spec.name == "SDL2"
        assert tool.spec.required_for == frozenset({Mode.DEV})
        assert tool.spec.version_args == ()  # No version check for libraries

    def test_repo(self) -> None:
        """Sdl2Tool uses correct GitHub repo."""
        tool = Sdl2Tool()

        assert tool.repo == "libsdl-org/SDL"

    def test_install_dir_name(self) -> None:
        """Sdl2Tool installs to 'sdl2' directory."""
        tool = Sdl2Tool()

        assert tool.install_dir_name() == "sdl2"

    def test_strip_components(self) -> None:
        """SDL2 archive has root directory to strip."""
        tool = Sdl2Tool()

        assert tool.strip_components() == 1

    def test_is_windows_only(self) -> None:
        """SDL2 auto-install is Windows-only."""
        tool = Sdl2Tool()

        assert tool.is_windows_only() is True


class TestSdl2ToolLatestVersion:
    """Tests for Sdl2Tool.latest_version()."""

    def test_success(self) -> None:
        """Fetch latest version from GitHub."""
        client = MockHttpClient()
        # SDL uses "release-X.Y.Z" tags
        client.set_json(
            "https://api.github.com/repos/libsdl-org/SDL/releases/latest",
            {"tag_name": "release-2.30.0"},
        )

        tool = Sdl2Tool()
        result = tool.latest_version(client)

        assert isinstance(result, Ok)
        # The tag gets 'v' stripped, so 'release-2.30.0' -> 'release-2.30.0'
        # Note: our github_latest_release strips 'v' prefix only
        assert result.value == "release-2.30.0"


class TestSdl2ToolDownloadUrl:
    """Tests for Sdl2Tool.download_url()."""

    def test_windows_x64(self) -> None:
        """Download URL for Windows x64 (MinGW)."""
        tool = Sdl2Tool()

        url = tool.download_url("2.30.0", Platform.WINDOWS, Arch.X64)

        assert (
            url
            == "https://github.com/libsdl-org/SDL/releases/download/release-2.30.0/SDL2-devel-2.30.0-mingw.zip"
        )

    def test_windows_arm64(self) -> None:
        """Download URL is same for Windows ARM64 (MinGW build)."""
        tool = Sdl2Tool()

        url = tool.download_url("2.30.0", Platform.WINDOWS, Arch.ARM64)

        # Same URL - we use MinGW build
        assert "SDL2-devel-2.30.0-mingw.zip" in url


class TestSdl2ToolBinPath:
    """Tests for Sdl2Tool.bin_path()."""

    def test_windows(self) -> None:
        """Binary (DLL) path on Windows (MinGW)."""
        tool = Sdl2Tool()

        path = tool.bin_path(Path("/tools"), Platform.WINDOWS)

        assert path == Path("/tools/sdl2/bin/SDL2.dll")

    def test_linux_returns_none(self) -> None:
        """bin_path returns None on Linux (system install)."""
        tool = Sdl2Tool()

        path = tool.bin_path(Path("/tools"), Platform.LINUX)

        assert path is None

    def test_macos_returns_none(self) -> None:
        """bin_path returns None on macOS (system install)."""
        tool = Sdl2Tool()

        path = tool.bin_path(Path("/tools"), Platform.MACOS)

        assert path is None


class TestSdl2ToolPaths:
    """Tests for Sdl2Tool include and lib paths."""

    def test_include_path(self) -> None:
        """include_path returns SDL2 headers location."""
        tool = Sdl2Tool()

        path = tool.include_path(Path("/tools"))

        assert path == Path("/tools/sdl2/include")

    def test_lib_path(self) -> None:
        """lib_path returns SDL2 library location (MinGW)."""
        tool = Sdl2Tool()

        path = tool.lib_path(Path("/tools"))

        assert path == Path("/tools/sdl2/lib")


class TestSdl2ToolIsInstalled:
    """Tests for Sdl2Tool.is_installed()."""

    def test_windows_installed(self, tmp_path: Path) -> None:
        """is_installed returns True when libSDL2.dll.a exists on Windows (MinGW)."""
        tool = Sdl2Tool()

        # Create libSDL2.dll.a in MinGW package structure
        lib_dir = tmp_path / "sdl2" / "lib"
        lib_dir.mkdir(parents=True)
        (lib_dir / "libSDL2.dll.a").touch()

        assert tool.is_installed(tmp_path, Platform.WINDOWS) is True

    def test_windows_not_installed(self, tmp_path: Path) -> None:
        """is_installed returns False when DLL doesn't exist."""
        tool = Sdl2Tool()

        assert tool.is_installed(tmp_path, Platform.WINDOWS) is False

    def test_linux_checks_system(self) -> None:
        """is_installed checks sdl2-config on Linux."""
        tool = Sdl2Tool()

        with patch("shutil.which", return_value="/usr/bin/sdl2-config"):
            assert tool.is_installed(Path("/tools"), Platform.LINUX) is True

        with patch("shutil.which", return_value=None):
            assert tool.is_installed(Path("/tools"), Platform.LINUX) is False

    def test_macos_checks_system(self) -> None:
        """is_installed checks sdl2-config on macOS."""
        tool = Sdl2Tool()

        with patch("shutil.which", return_value="/usr/local/bin/sdl2-config"):
            assert tool.is_installed(Path("/tools"), Platform.MACOS) is True


class TestSdl2ToolInstallHints:
    """Tests for Sdl2Tool install hints."""

    def test_linux_hint(self) -> None:
        """Get Linux install hint."""
        tool = Sdl2Tool()

        hint = tool.get_install_hint(Platform.LINUX)

        assert hint == "sudo apt install libsdl2-dev"

    def test_macos_hint(self) -> None:
        """Get macOS install hint."""
        tool = Sdl2Tool()

        hint = tool.get_install_hint(Platform.MACOS)

        assert hint == "brew install sdl2"

    def test_windows_no_hint(self) -> None:
        """Windows has no hint (auto-installed)."""
        tool = Sdl2Tool()

        hint = tool.get_install_hint(Platform.WINDOWS)

        assert hint is None
