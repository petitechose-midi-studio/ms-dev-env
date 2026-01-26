"""Tests for WrapperGenerator."""

import sys
from pathlib import Path

import pytest

from ms.platform.detection import Platform
from ms.tools.wrapper import (
    WrapperGenerator,
    WrapperSpec,
    create_emscripten_wrappers,
)


@pytest.fixture
def generator(tmp_path: Path) -> WrapperGenerator:
    """Create a generator with temp bin dir."""
    bin_dir = tmp_path / "bin"
    return WrapperGenerator(bin_dir)


class TestWrapperSpec:
    """Tests for WrapperSpec dataclass."""

    def test_creation(self) -> None:
        """WrapperSpec can be created."""
        spec = WrapperSpec(
            name="test",
            target=Path("/usr/bin/test"),
            args=("arg1", "arg2"),
            env={"VAR": "value"},
        )

        assert spec.name == "test"
        assert spec.target == Path("/usr/bin/test")
        assert spec.args == ("arg1", "arg2")
        assert spec.env == {"VAR": "value"}

    def test_defaults(self) -> None:
        """WrapperSpec has sensible defaults."""
        spec = WrapperSpec(name="test", target=Path("/usr/bin/test"))

        assert spec.args == ()
        assert spec.env is None

    def test_frozen(self) -> None:
        """WrapperSpec is frozen (immutable)."""
        spec = WrapperSpec(name="test", target=Path("/usr/bin/test"))

        with pytest.raises(AttributeError):
            spec.name = "other"  # type: ignore


class TestWrapperGenerator:
    """Tests for WrapperGenerator."""

    def test_init(self, tmp_path: Path) -> None:
        """Generator initializes correctly."""
        bin_dir = tmp_path / "bin"
        generator = WrapperGenerator(bin_dir)

        assert generator.bin_dir == bin_dir

    def test_creates_bin_dir(self, tmp_path: Path) -> None:
        """Generator creates bin directory if needed."""
        bin_dir = tmp_path / "bin"
        generator = WrapperGenerator(bin_dir)

        spec = WrapperSpec(name="test", target=Path("/usr/bin/test"))
        generator.generate(spec, Platform.LINUX)

        assert bin_dir.exists()


class TestBashGeneration:
    """Tests for bash script generation."""

    def test_generates_bash_on_linux(self, generator: WrapperGenerator) -> None:
        """Generates bash script on Linux."""
        spec = WrapperSpec(name="test", target=Path("/usr/bin/test"))

        path = generator.generate(spec, Platform.LINUX)

        assert path.exists()
        assert path.name == "test"

    def test_generates_bash_on_macos(self, generator: WrapperGenerator) -> None:
        """Generates bash script on macOS."""
        spec = WrapperSpec(name="test", target=Path("/usr/bin/test"))

        path = generator.generate(spec, Platform.MACOS)

        assert path.exists()
        assert path.name == "test"

    def test_bash_has_shebang(self, generator: WrapperGenerator) -> None:
        """Bash script has shebang line."""
        spec = WrapperSpec(name="test", target=Path("/usr/bin/test"))

        path = generator.generate(spec, Platform.LINUX)
        content = path.read_text()

        assert content.startswith("#!/usr/bin/env bash")

    def test_bash_uses_lf_endings(self, generator: WrapperGenerator) -> None:
        """Bash script uses LF line endings."""
        spec = WrapperSpec(name="test", target=Path("/usr/bin/test"))

        path = generator.generate(spec, Platform.LINUX)
        content = path.read_bytes()

        assert b"\r\n" not in content
        assert b"\n" in content

    def test_bash_includes_exec(self, generator: WrapperGenerator) -> None:
        """Bash script uses exec to replace shell."""
        spec = WrapperSpec(name="test", target=Path("/usr/bin/test"))

        path = generator.generate(spec, Platform.LINUX)
        content = path.read_text()

        assert "exec" in content
        # Path separator may vary by platform
        assert "test" in content and ("usr" in content or "bin" in content)

    def test_bash_with_args(self, generator: WrapperGenerator) -> None:
        """Bash script includes additional arguments."""
        spec = WrapperSpec(
            name="my-tool",
            target=Path("/tools/my-tool/bin"),
            args=("subcommand",),
        )

        path = generator.generate(spec, Platform.LINUX)
        content = path.read_text()

        assert '"subcommand"' in content
        assert '"$@"' in content

    def test_bash_with_env(self, generator: WrapperGenerator) -> None:
        """Bash script sets environment variables."""
        spec = WrapperSpec(
            name="test",
            target=Path("/usr/bin/test"),
            env={"FOO": "bar", "BAZ": "qux"},
        )

        path = generator.generate(spec, Platform.LINUX)
        content = path.read_text()

        assert 'export FOO="bar"' in content
        assert 'export BAZ="qux"' in content

    @pytest.mark.skipif(sys.platform == "win32", reason="chmod doesn't work on Windows")
    def test_bash_is_executable(self, generator: WrapperGenerator) -> None:
        """Bash script is executable."""
        spec = WrapperSpec(name="test", target=Path("/usr/bin/test"))

        path = generator.generate(spec, Platform.LINUX)

        assert path.stat().st_mode & 0o111


class TestCmdGeneration:
    """Tests for cmd script generation."""

    def test_generates_cmd_on_windows(self, generator: WrapperGenerator) -> None:
        """Generates cmd script on Windows."""
        spec = WrapperSpec(name="test", target=Path("C:/tools/test.exe"))

        path = generator.generate(spec, Platform.WINDOWS)

        assert path.exists()
        assert path.name == "test.cmd"

    def test_cmd_starts_with_echo_off(self, generator: WrapperGenerator) -> None:
        """Cmd script starts with @echo off."""
        spec = WrapperSpec(name="test", target=Path("C:/tools/test.exe"))

        path = generator.generate(spec, Platform.WINDOWS)
        content = path.read_text()

        assert content.startswith("@echo off")

    def test_cmd_uses_crlf_endings(self, generator: WrapperGenerator) -> None:
        """Cmd script uses CRLF line endings."""
        spec = WrapperSpec(name="test", target=Path("C:/tools/test.exe"))

        path = generator.generate(spec, Platform.WINDOWS)
        content = path.read_bytes()

        assert b"\r\n" in content

    def test_cmd_includes_target(self, generator: WrapperGenerator) -> None:
        """Cmd script includes target path."""
        spec = WrapperSpec(name="test", target=Path("C:/tools/test.exe"))

        path = generator.generate(spec, Platform.WINDOWS)
        content = path.read_text()

        assert '"C:\\tools\\test.exe"' in content or '"C:/tools/test.exe"' in content

    def test_cmd_with_args(self, generator: WrapperGenerator) -> None:
        """Cmd script includes additional arguments."""
        spec = WrapperSpec(
            name="my-tool",
            target=Path("C:/tools/my-tool.exe"),
            args=("subcommand",),
        )

        path = generator.generate(spec, Platform.WINDOWS)
        content = path.read_text()

        assert '"subcommand"' in content
        assert "%*" in content

    def test_cmd_with_env(self, generator: WrapperGenerator) -> None:
        """Cmd script sets environment variables."""
        spec = WrapperSpec(
            name="test",
            target=Path("C:/tools/test.exe"),
            env={"FOO": "bar"},
        )

        path = generator.generate(spec, Platform.WINDOWS)
        content = path.read_text()

        assert 'set "FOO=bar"' in content


class TestGenerateAll:
    """Tests for generate_all method."""

    def test_generates_multiple(self, generator: WrapperGenerator) -> None:
        """generate_all creates multiple wrappers."""
        specs = [
            WrapperSpec(name="tool1", target=Path("/tools/tool1")),
            WrapperSpec(name="tool2", target=Path("/tools/tool2")),
        ]

        paths = generator.generate_all(specs, Platform.LINUX)

        assert len(paths) == 2
        assert all(p.exists() for p in paths)


class TestCreateEmscriptenWrappers:
    """Tests for create_emscripten_wrappers helper."""

    def test_creates_emcc_and_emcmake(self, tmp_path: Path) -> None:
        """Creates emcc and emcmake wrappers."""
        emsdk_dir = tmp_path / "emsdk"
        bin_dir = tmp_path / "bin"

        paths = create_emscripten_wrappers(emsdk_dir, bin_dir, Platform.LINUX)

        assert len(paths) == 2
        names = {p.name for p in paths}
        assert "emcc" in names
        assert "emcmake" in names

    def test_wrappers_set_emsdk_env(self, tmp_path: Path) -> None:
        """Wrappers set EMSDK environment variable."""
        emsdk_dir = tmp_path / "emsdk"
        bin_dir = tmp_path / "bin"

        paths = create_emscripten_wrappers(emsdk_dir, bin_dir, Platform.LINUX)

        for path in paths:
            content = path.read_text()
            assert "EMSDK" in content
            assert str(emsdk_dir) in content
