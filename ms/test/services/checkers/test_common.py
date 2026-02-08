# SPDX-License-Identifier: MIT
"""Tests for common checker utilities."""

from pathlib import Path

import pytest

from ms.platform.detection import LinuxDistro, Platform
from ms.services.checkers.common import (
    DefaultCommandRunner,
    Hints,
    first_line,
    format_version_triplet,
    get_platform_key,
    load_hints,
    parse_version_triplet,
)


class TestFirstLine:
    """Tests for first_line helper."""

    def test_single_line(self) -> None:
        assert first_line("hello") == "hello"

    def test_multiple_lines(self) -> None:
        assert first_line("first\nsecond\nthird") == "first"

    def test_empty_string(self) -> None:
        assert first_line("") == ""

    def test_whitespace_only(self) -> None:
        assert first_line("   \n   \n   ") == ""

    def test_leading_whitespace(self) -> None:
        assert first_line("  hello  \nworld") == "hello"

    def test_blank_lines_before_content(self) -> None:
        assert first_line("\n\n  content  \n") == "content"


class TestGetPlatformKey:
    """Tests for get_platform_key helper."""

    def test_linux_debian(self) -> None:
        assert get_platform_key(Platform.LINUX, LinuxDistro.DEBIAN) == "debian"

    def test_linux_fedora(self) -> None:
        assert get_platform_key(Platform.LINUX, LinuxDistro.FEDORA) == "fedora"

    def test_linux_arch(self) -> None:
        assert get_platform_key(Platform.LINUX, LinuxDistro.ARCH) == "arch"

    def test_linux_suse(self) -> None:
        # SUSE maps to fedora as closest match
        assert get_platform_key(Platform.LINUX, LinuxDistro.SUSE) == "fedora"

    def test_linux_unknown(self) -> None:
        assert get_platform_key(Platform.LINUX, LinuxDistro.UNKNOWN) == "debian"

    def test_linux_no_distro(self) -> None:
        assert get_platform_key(Platform.LINUX, None) == "debian"

    def test_macos(self) -> None:
        assert get_platform_key(Platform.MACOS) == "macos"

    def test_windows(self) -> None:
        assert get_platform_key(Platform.WINDOWS) == "windows"

    def test_unknown_platform(self) -> None:
        assert get_platform_key(Platform.UNKNOWN) == "debian"


class TestVersionTriplet:
    def test_parse_triplet_found(self) -> None:
        assert parse_version_triplet("rustc 1.93.0 (abcdef 2026-01-01)") == (1, 93, 0)

    def test_parse_triplet_missing(self) -> None:
        assert parse_version_triplet("no version here") is None

    def test_format_triplet(self) -> None:
        assert format_version_triplet((1, 2, 3)) == "1.2.3"


class TestHints:
    """Tests for Hints dataclass."""

    def test_empty_hints(self) -> None:
        hints = Hints.empty()
        assert hints.tools == {}
        assert hints.system == {}
        assert hints.runtime == {}

    def test_get_tool_hint_found(self) -> None:
        hints = Hints(
            tools={
                "cmake": {"debian": "sudo apt install cmake", "fedora": "sudo dnf install cmake"}
            }
        )
        assert hints.get_tool_hint("cmake", "debian") == "sudo apt install cmake"
        assert hints.get_tool_hint("cmake", "fedora") == "sudo dnf install cmake"

    def test_get_tool_hint_not_found(self) -> None:
        hints = Hints(tools={"cmake": {"debian": "apt install cmake"}})
        assert hints.get_tool_hint("cmake", "windows") is None
        assert hints.get_tool_hint("ninja", "debian") is None

    def test_get_system_hint_found(self) -> None:
        hints = Hints(system={"sdl2": {"debian": "sudo apt install libsdl2-dev"}})
        assert hints.get_system_hint("sdl2", "debian") == "sudo apt install libsdl2-dev"

    def test_get_system_hint_not_found(self) -> None:
        hints = Hints.empty()
        assert hints.get_system_hint("sdl2", "debian") is None

    def test_get_runtime_hint_found(self) -> None:
        hints = Hints(runtime={"virmidi": {"linux": "sudo modprobe snd-virmidi"}})
        assert hints.get_runtime_hint("virmidi", "linux") == "sudo modprobe snd-virmidi"

    def test_get_runtime_hint_not_found(self) -> None:
        hints = Hints.empty()
        assert hints.get_runtime_hint("virmidi", "linux") is None

    def test_frozen(self) -> None:
        hints = Hints.empty()
        with pytest.raises(AttributeError):
            hints.tools = {}  # type: ignore[misc]


class TestLoadHints:
    """Tests for load_hints function."""

    def test_load_from_default_path(self) -> None:
        # Should load the actual hints.toml from ms/data/
        hints = load_hints()
        # Verify some known entries exist
        assert hints.get_tool_hint("cmake", "debian") is not None
        assert hints.get_system_hint("sdl2", "debian") is not None

    def test_load_nonexistent_path(self, tmp_path: Path) -> None:
        hints = load_hints(tmp_path / "nonexistent.toml")
        assert hints == Hints.empty()

    def test_load_valid_toml(self, tmp_path: Path) -> None:
        toml_content = """
[tools.cmake]
debian = "apt install cmake"
fedora = "dnf install cmake"

[system.sdl2]
debian = "apt install libsdl2-dev"

[runtime.midi]
macos = "Enable IAC Driver"
"""
        toml_path = tmp_path / "hints.toml"
        toml_path.write_text(toml_content)

        hints = load_hints(toml_path)
        assert hints.get_tool_hint("cmake", "debian") == "apt install cmake"
        assert hints.get_tool_hint("cmake", "fedora") == "dnf install cmake"
        assert hints.get_system_hint("sdl2", "debian") == "apt install libsdl2-dev"
        assert hints.get_runtime_hint("midi", "macos") == "Enable IAC Driver"

    def test_load_invalid_toml(self, tmp_path: Path) -> None:
        toml_path = tmp_path / "invalid.toml"
        toml_path.write_text("this is not valid toml [[[[")

        hints = load_hints(toml_path)
        assert hints == Hints.empty()

    def test_load_empty_file(self, tmp_path: Path) -> None:
        toml_path = tmp_path / "empty.toml"
        toml_path.write_text("")

        hints = load_hints(toml_path)
        assert hints == Hints.empty()


class TestDefaultCommandRunner:
    """Tests for DefaultCommandRunner."""

    def test_run_successful_command(self) -> None:
        import sys

        runner = DefaultCommandRunner()
        result = runner.run([sys.executable, "--version"])
        assert result.returncode == 0
        assert "Python" in result.stdout or "Python" in result.stderr

    def test_run_with_cwd(self, tmp_path: Path) -> None:
        import sys

        runner = DefaultCommandRunner()
        result = runner.run(
            [sys.executable, "-c", "import os; print(os.getcwd())"],
            cwd=tmp_path,
        )
        assert result.returncode == 0
        assert str(tmp_path) in result.stdout or tmp_path.name in result.stdout

    def test_run_nonexistent_command(self) -> None:
        runner = DefaultCommandRunner()
        # This should raise FileNotFoundError
        with pytest.raises(FileNotFoundError):
            runner.run(["nonexistent_command_12345"])
