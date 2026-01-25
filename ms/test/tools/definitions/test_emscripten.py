"""Tests for EmscriptenTool."""

from pathlib import Path

from ms.core.result import Ok
from ms.platform.detection import Arch, Platform
from ms.tools.base import Mode
from ms.tools.definitions.emscripten import EmscriptenTool
from ms.tools.http import MockHttpClient


class TestEmscriptenTool:
    """Tests for EmscriptenTool."""

    def test_spec(self) -> None:
        """EmscriptenTool has correct spec."""
        tool = EmscriptenTool()

        assert tool.spec.id == "emscripten"
        assert tool.spec.name == "Emscripten SDK"
        assert tool.spec.required_for == frozenset({Mode.DEV})

    def test_repo(self) -> None:
        """EmscriptenTool uses correct GitHub repo."""
        tool = EmscriptenTool()

        assert tool.repo == "emscripten-core/emsdk"
        assert "github.com" in tool.repo_url

    def test_install_dir_name(self) -> None:
        """EmscriptenTool installs to 'emsdk' directory."""
        tool = EmscriptenTool()

        assert tool.install_dir_name() == "emsdk"

    def test_uses_git_install(self) -> None:
        """EmscriptenTool uses git-based installation."""
        tool = EmscriptenTool()

        assert tool.uses_git_install() is True


class TestEmscriptenToolLatestVersion:
    """Tests for EmscriptenTool.latest_version()."""

    def test_success(self) -> None:
        """Version is a sentinel; install uses `emsdk install latest`."""
        client = MockHttpClient()

        tool = EmscriptenTool()
        result = tool.latest_version(client)

        assert isinstance(result, Ok)
        assert result.value == "latest"


class TestEmscriptenToolDownloadUrl:
    """Tests for EmscriptenTool.download_url()."""

    def test_returns_git_url(self) -> None:
        """download_url returns git clone URL."""
        tool = EmscriptenTool()

        url = tool.download_url("3.1.50", Platform.LINUX, Arch.X64)

        assert url == "https://github.com/emscripten-core/emsdk.git"


class TestEmscriptenToolBinPath:
    """Tests for EmscriptenTool.bin_path()."""

    def test_linux(self) -> None:
        """Binary path on Linux."""
        tool = EmscriptenTool()

        path = tool.bin_path(Path("/tools"), Platform.LINUX)

        assert path == Path("/tools/emsdk/upstream/emscripten/emcc")

    def test_macos(self) -> None:
        """Binary path on macOS."""
        tool = EmscriptenTool()

        path = tool.bin_path(Path("/tools"), Platform.MACOS)

        assert path == Path("/tools/emsdk/upstream/emscripten/emcc")

    def test_windows(self) -> None:
        """Binary path on Windows uses .bat."""
        tool = EmscriptenTool()

        path = tool.bin_path(Path("/tools"), Platform.WINDOWS)

        assert path == Path("/tools/emsdk/upstream/emscripten/emcc.bat")


class TestEmscriptenToolPaths:
    """Tests for EmscriptenTool helper paths."""

    def test_emcmake_path_unix(self) -> None:
        """emcmake path on Unix."""
        tool = EmscriptenTool()

        path = tool.emcmake_path(Path("/tools"), Platform.LINUX)

        assert path == Path("/tools/emsdk/upstream/emscripten/emcmake")

    def test_emcmake_path_windows(self) -> None:
        """emcmake path on Windows."""
        tool = EmscriptenTool()

        path = tool.emcmake_path(Path("/tools"), Platform.WINDOWS)

        assert path == Path("/tools/emsdk/upstream/emscripten/emcmake.bat")

    def test_emsdk_path_unix(self) -> None:
        """emsdk script path on Unix."""
        tool = EmscriptenTool()

        path = tool.emsdk_path(Path("/tools"), Platform.LINUX)

        assert path == Path("/tools/emsdk/emsdk")

    def test_emsdk_path_windows(self) -> None:
        """emsdk script path on Windows."""
        tool = EmscriptenTool()

        path = tool.emsdk_path(Path("/tools"), Platform.WINDOWS)

        assert path == Path("/tools/emsdk/emsdk.bat")

    def test_emsdk_env_path_unix(self) -> None:
        """emsdk_env script path on Unix."""
        tool = EmscriptenTool()

        path = tool.emsdk_env_path(Path("/tools"), Platform.LINUX)

        assert path == Path("/tools/emsdk/emsdk_env.sh")

    def test_emsdk_env_path_windows(self) -> None:
        """emsdk_env script path on Windows."""
        tool = EmscriptenTool()

        path = tool.emsdk_env_path(Path("/tools"), Platform.WINDOWS)

        assert path == Path("/tools/emsdk/emsdk_env.bat")

    def test_emsdk_home(self) -> None:
        """emsdk_home returns EMSDK path."""
        tool = EmscriptenTool()

        path = tool.emsdk_home(Path("/tools"))

        assert path == Path("/tools/emsdk")


class TestEmscriptenToolIsInstalled:
    """Tests for EmscriptenTool.is_installed()."""

    def test_installed_with_emcc(self, tmp_path: Path) -> None:
        """is_installed returns True when emcc exists."""
        tool = EmscriptenTool()

        # Create emcc binary
        emcc_dir = tmp_path / "emsdk" / "upstream" / "emscripten"
        emcc_dir.mkdir(parents=True)
        (emcc_dir / "emcc").touch()

        assert tool.is_installed(tmp_path, Platform.LINUX) is True

    def test_not_installed_no_emsdk(self, tmp_path: Path) -> None:
        """is_installed returns False when emsdk dir doesn't exist."""
        tool = EmscriptenTool()

        assert tool.is_installed(tmp_path, Platform.LINUX) is False

    def test_not_installed_no_emcc(self, tmp_path: Path) -> None:
        """is_installed returns False when emsdk exists but not activated."""
        tool = EmscriptenTool()

        # Create emsdk dir but not emcc
        emsdk_dir = tmp_path / "emsdk"
        emsdk_dir.mkdir()

        assert tool.is_installed(tmp_path, Platform.LINUX) is False

    def test_windows_checks_bat(self, tmp_path: Path) -> None:
        """is_installed checks for .bat on Windows."""
        tool = EmscriptenTool()

        # Create emcc.bat
        emcc_dir = tmp_path / "emsdk" / "upstream" / "emscripten"
        emcc_dir.mkdir(parents=True)
        (emcc_dir / "emcc.bat").touch()

        assert tool.is_installed(tmp_path, Platform.WINDOWS) is True


class TestEmscriptenToolIsCloned:
    """Tests for EmscriptenTool.is_cloned()."""

    def test_cloned_with_git_dir(self, tmp_path: Path) -> None:
        """is_cloned returns True when .git exists."""
        tool = EmscriptenTool()

        # Create .git directory
        git_dir = tmp_path / "emsdk" / ".git"
        git_dir.mkdir(parents=True)

        assert tool.is_cloned(tmp_path) is True

    def test_not_cloned(self, tmp_path: Path) -> None:
        """is_cloned returns False when no .git."""
        tool = EmscriptenTool()

        assert tool.is_cloned(tmp_path) is False


class TestEmscriptenToolInstallCommands:
    """Tests for EmscriptenTool.get_install_commands()."""

    def test_full_install_unix(self, tmp_path: Path) -> None:
        """Full install commands on Unix (not cloned)."""
        tool = EmscriptenTool()

        commands = tool.get_install_commands(tmp_path, Platform.LINUX)

        assert len(commands) == 3
        # Clone command
        assert commands[0][0] == "git"
        assert commands[0][1] == "clone"
        # Install command
        assert "install" in commands[1]
        assert "latest" in commands[1]
        # Activate command
        assert "activate" in commands[2]
        assert "latest" in commands[2]

    def test_partial_install_unix(self, tmp_path: Path) -> None:
        """Install commands on Unix (already cloned)."""
        tool = EmscriptenTool()

        # Create .git to simulate cloned repo
        git_dir = tmp_path / "emsdk" / ".git"
        git_dir.mkdir(parents=True)

        commands = tool.get_install_commands(tmp_path, Platform.LINUX)

        assert len(commands) == 2  # No clone command
        assert "install" in commands[0]
        assert "activate" in commands[1]

    def test_windows_uses_bat(self, tmp_path: Path) -> None:
        """Install commands on Windows use .bat."""
        tool = EmscriptenTool()

        # Create .git to simulate cloned repo
        git_dir = tmp_path / "emsdk" / ".git"
        git_dir.mkdir(parents=True)

        commands = tool.get_install_commands(tmp_path, Platform.WINDOWS)

        # Check emsdk.bat is used
        assert commands[0][0].endswith("emsdk.bat")
