# SPDX-License-Identifier: MIT
"""Tests for SystemChecker."""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from ms.platform.detection import LinuxDistro, Platform
from ms.services.checkers.base import CheckStatus
from ms.services.checkers.common import Hints
from ms.services.checkers.system import SystemChecker


class MockCommandRunner:
    """Mock command runner for testing."""

    def __init__(self, responses: dict[tuple[str, ...], tuple[int, str, str]] | None = None):
        """Initialize with canned responses."""
        self.responses = responses or {}
        self.calls: list[list[str]] = []

    def run(
        self, args: list[str], *, capture: bool = True, cwd: Path | None = None
    ) -> subprocess.CompletedProcess[str]:
        """Return canned response for command."""
        self.calls.append(args)
        key = tuple(args)
        if key in self.responses:
            rc, stdout, stderr = self.responses[key]
            return subprocess.CompletedProcess(args, rc, stdout, stderr)
        # Default: command failed
        return subprocess.CompletedProcess(args, 1, "", "")


class TestSystemCheckerLinux:
    """Tests for Linux system dependency checks."""

    def test_pkg_config_missing(self) -> None:
        checker = SystemChecker(platform=Platform.LINUX)
        with patch("shutil.which", return_value=None):
            results = checker.check_all()

        # pkg-config error, SDL2/ALSA/libudev warnings, C/C++ compiler errors
        assert len(results) == 6
        assert results[0].name == "pkg-config"
        assert results[0].status == CheckStatus.ERROR
        assert results[1].name == "SDL2"
        assert results[1].status == CheckStatus.WARNING
        assert results[2].name == "ALSA"
        assert results[2].status == CheckStatus.WARNING
        assert results[3].name == "libudev"
        assert results[3].status == CheckStatus.WARNING
        assert results[4].name == "C compiler"
        assert results[4].status == CheckStatus.ERROR
        assert results[5].name == "C++ compiler"
        assert results[5].status == CheckStatus.ERROR

    def test_sdl2_and_alsa_found(self) -> None:
        runner = MockCommandRunner(
            {
                ("pkg-config", "--exists", "sdl2"): (0, "", ""),
                ("pkg-config", "--modversion", "sdl2"): (0, "2.28.5", ""),
                ("pkg-config", "--exists", "alsa"): (0, "", ""),
                ("pkg-config", "--modversion", "alsa"): (0, "1.2.10", ""),
                ("pkg-config", "--exists", "libudev"): (0, "", ""),
                ("pkg-config", "--modversion", "libudev"): (0, "255", ""),
                ("cc", "--version"): (0, "cc 1.0", ""),
                ("c++", "--version"): (0, "c++ 1.0", ""),
            }
        )
        checker = SystemChecker(platform=Platform.LINUX, runner=runner)

        def which(name: str) -> str | None:
            return {
                "pkg-config": "/usr/bin/pkg-config",
                "cc": "/usr/bin/cc",
                "c++": "/usr/bin/c++",
            }.get(name)

        with patch(
            "shutil.which",
            side_effect=which,
        ):
            results = checker.check_all()

        assert len(results) == 6
        assert results[0].name == "pkg-config"
        assert results[0].status == CheckStatus.OK
        assert results[1].name == "SDL2"
        assert results[1].status == CheckStatus.OK
        assert "2.28.5" in results[1].message
        assert results[2].name == "ALSA"
        assert results[2].status == CheckStatus.OK
        assert "1.2.10" in results[2].message
        assert results[3].name == "libudev"
        assert results[3].status == CheckStatus.OK
        assert "255" in results[3].message
        assert results[4].name == "C compiler"
        assert results[4].status == CheckStatus.OK
        assert results[5].name == "C++ compiler"
        assert results[5].status == CheckStatus.OK

    def test_sdl2_missing(self) -> None:
        hints = Hints(system={"sdl2": {"debian": "sudo apt install libsdl2-dev"}})
        runner = MockCommandRunner(
            {
                ("pkg-config", "--exists", "sdl2"): (1, "", "No package 'sdl2' found"),
                ("pkg-config", "--exists", "alsa"): (0, "", ""),
                ("pkg-config", "--modversion", "alsa"): (0, "1.2.10", ""),
                ("pkg-config", "--exists", "libudev"): (0, "", ""),
                ("pkg-config", "--modversion", "libudev"): (0, "255", ""),
                ("cc", "--version"): (0, "cc 1.0", ""),
                ("c++", "--version"): (0, "c++ 1.0", ""),
            }
        )
        checker = SystemChecker(
            platform=Platform.LINUX,
            distro=LinuxDistro.DEBIAN,
            hints=hints,
            runner=runner,
        )

        def which(name: str) -> str | None:
            return {
                "pkg-config": "/usr/bin/pkg-config",
                "cc": "/usr/bin/cc",
                "c++": "/usr/bin/c++",
            }.get(name)

        with patch(
            "shutil.which",
            side_effect=which,
        ):
            results = checker.check_all()

        sdl2_result = next(r for r in results if r.name == "SDL2")
        assert sdl2_result.status == CheckStatus.ERROR
        assert sdl2_result.hint == "sudo apt install libsdl2-dev"

    def test_alsa_missing(self) -> None:
        hints = Hints(system={"alsa": {"fedora": "sudo dnf install alsa-lib-devel"}})
        runner = MockCommandRunner(
            {
                ("pkg-config", "--exists", "sdl2"): (0, "", ""),
                ("pkg-config", "--modversion", "sdl2"): (0, "2.28.5", ""),
                ("pkg-config", "--exists", "alsa"): (1, "", "No package 'alsa' found"),
                ("pkg-config", "--exists", "libudev"): (0, "", ""),
                ("pkg-config", "--modversion", "libudev"): (0, "255", ""),
                ("cc", "--version"): (0, "cc 1.0", ""),
                ("c++", "--version"): (0, "c++ 1.0", ""),
            }
        )
        checker = SystemChecker(
            platform=Platform.LINUX,
            distro=LinuxDistro.FEDORA,
            hints=hints,
            runner=runner,
        )

        def which(name: str) -> str | None:
            return {
                "pkg-config": "/usr/bin/pkg-config",
                "cc": "/usr/bin/cc",
                "c++": "/usr/bin/c++",
            }.get(name)

        with patch(
            "shutil.which",
            side_effect=which,
        ):
            results = checker.check_all()

        alsa_result = next(r for r in results if r.name == "ALSA")
        assert alsa_result.status == CheckStatus.ERROR
        assert alsa_result.hint == "sudo dnf install alsa-lib-devel"


class TestSystemCheckerMacOS:
    """Tests for macOS system dependency checks."""

    def test_xcode_clt_missing(self) -> None:
        runner = MockCommandRunner(
            {
                ("xcode-select", "-p"): (1, "", ""),
            }
        )
        checker = SystemChecker(platform=Platform.MACOS, runner=runner)

        def which(name: str) -> str | None:
            return {
                "xcode-select": "/usr/bin/xcode-select",
            }.get(name)

        with patch(
            "shutil.which",
            side_effect=which,
        ):
            results = checker.check_all()

        assert len(results) == 4
        assert results[0].name == "Xcode CLT"
        assert results[0].status == CheckStatus.ERROR
        assert "xcode-select --install" in (results[0].hint or "")
        assert results[1].name == "SDL2"
        assert results[1].status == CheckStatus.WARNING
        assert results[2].name == "C compiler"
        assert results[2].status == CheckStatus.ERROR
        assert results[3].name == "C++ compiler"
        assert results[3].status == CheckStatus.ERROR

    def test_sdl2_installed(self) -> None:
        runner = MockCommandRunner(
            {
                ("xcode-select", "-p"): (0, "/Library/Developer/CommandLineTools", ""),
                ("pkg-config", "--exists", "sdl2"): (0, "", ""),
                ("pkg-config", "--modversion", "sdl2"): (0, "2.28.5", ""),
                ("cc", "--version"): (0, "cc 1.0", ""),
                ("c++", "--version"): (0, "c++ 1.0", ""),
            }
        )
        checker = SystemChecker(platform=Platform.MACOS, runner=runner)

        def which(name: str) -> str | None:
            return {
                "xcode-select": "/usr/bin/xcode-select",
                "pkg-config": "/opt/homebrew/bin/pkg-config",
                "cc": "/usr/bin/cc",
                "c++": "/usr/bin/c++",
            }.get(name)

        with patch(
            "shutil.which",
            side_effect=which,
        ):
            results = checker.check_all()

        assert len(results) == 4
        assert results[0].name == "Xcode CLT"
        assert results[0].status == CheckStatus.OK
        assert results[1].name == "SDL2"
        assert results[1].status == CheckStatus.OK
        assert "2.28.5" in results[1].message
        assert results[2].name == "C compiler"
        assert results[2].status == CheckStatus.OK
        assert results[3].name == "C++ compiler"
        assert results[3].status == CheckStatus.OK

    def test_sdl2_missing(self) -> None:
        hints = Hints(system={"sdl2": {"macos": "brew install sdl2"}})
        runner = MockCommandRunner(
            {
                ("xcode-select", "-p"): (0, "/Library/Developer/CommandLineTools", ""),
                ("pkg-config", "--exists", "sdl2"): (1, "", "No package 'sdl2' found"),
                ("cc", "--version"): (0, "cc 1.0", ""),
                ("c++", "--version"): (0, "c++ 1.0", ""),
            }
        )
        checker = SystemChecker(platform=Platform.MACOS, hints=hints, runner=runner)

        def which(name: str) -> str | None:
            return {
                "xcode-select": "/usr/bin/xcode-select",
                "pkg-config": "/opt/homebrew/bin/pkg-config",
                "cc": "/usr/bin/cc",
                "c++": "/usr/bin/c++",
            }.get(name)

        with patch(
            "shutil.which",
            side_effect=which,
        ):
            results = checker.check_all()

        sdl2_result = next(r for r in results if r.name == "SDL2")
        assert sdl2_result.status == CheckStatus.WARNING
        assert sdl2_result.hint == "brew install sdl2"


class TestSystemCheckerWindows:
    """Tests for Windows system dependency checks."""

    def test_sdl2_bundled_found(self, tmp_path: Path) -> None:
        tools_dir = tmp_path / "tools"
        # SDL2 VC package structure: tools/sdl2/lib/
        sdl2_dir = tools_dir / "sdl2" / "lib"
        sdl2_dir.mkdir(parents=True)

        checker = SystemChecker(platform=Platform.WINDOWS, tools_dir=tools_dir)
        with patch("shutil.which", return_value=None):
            results = checker.check_all()

        assert len(results) == 2
        assert results[0].name == "SDL2"
        assert results[0].status == CheckStatus.OK
        assert "bundled" in results[0].message
        assert results[1].name == "C compiler"

    def test_sdl2_bundled_with_include(self, tmp_path: Path) -> None:
        tools_dir = tmp_path / "tools"
        # SDL2 VC package also has include dir
        sdl2_dir = tools_dir / "sdl2" / "include"
        sdl2_dir.mkdir(parents=True)

        checker = SystemChecker(platform=Platform.WINDOWS, tools_dir=tools_dir)
        with patch("shutil.which", return_value=None):
            results = checker.check_all()

        assert len(results) == 2
        assert results[0].name == "SDL2"
        assert results[0].status == CheckStatus.OK

    def test_sdl2_not_found(self, tmp_path: Path) -> None:
        tools_dir = tmp_path / "tools"
        tools_dir.mkdir()

        checker = SystemChecker(platform=Platform.WINDOWS, tools_dir=tools_dir)
        with patch("shutil.which", return_value=None):
            results = checker.check_all()

        assert len(results) == 2
        assert results[0].name == "SDL2"
        assert results[0].status == CheckStatus.WARNING
        assert "ms sync --tools" in (results[0].hint or "")
        assert results[1].name == "C compiler"

    def test_no_tools_dir(self) -> None:
        checker = SystemChecker(platform=Platform.WINDOWS, tools_dir=None)
        with patch("shutil.which", return_value=None):
            results = checker.check_all()

        assert len(results) == 2
        assert results[0].name == "SDL2"
        assert results[0].status == CheckStatus.WARNING
        assert "tools_dir not set" in results[0].message
        assert results[1].name == "C compiler"


class TestSystemCheckerUnknownPlatform:
    """Tests for unknown platform behavior."""

    def test_unknown_returns_empty(self) -> None:
        checker = SystemChecker(platform=Platform.UNKNOWN)
        results = checker.check_all()
        assert results == []


class TestSystemCheckerFrozen:
    """Tests for dataclass immutability."""

    def test_frozen(self) -> None:
        checker = SystemChecker(platform=Platform.LINUX)
        with pytest.raises(AttributeError):
            checker.platform = Platform.WINDOWS  # type: ignore[misc]
