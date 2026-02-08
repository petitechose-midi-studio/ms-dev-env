# SPDX-License-Identifier: MIT
# pyright: reportPrivateUsage=false
"""Tests for RuntimeChecker."""

from __future__ import annotations

import subprocess
from collections.abc import Callable
from pathlib import Path
from unittest.mock import patch

import pytest

from ms.platform.detection import LinuxDistro, Platform
from ms.services.checkers.base import CheckStatus
from ms.services.checkers.common import Hints
from ms.services.checkers.runtime import RuntimeChecker


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
        # Default: command not found
        raise FileNotFoundError(f"Command not found: {args[0]}")


def _which_factory(available: dict[str, str]) -> Callable[[str], str | None]:
    """Create a which mock that returns paths for available commands."""

    def mock_which(name: str) -> str | None:
        return available.get(name)

    return mock_which


class TestRuntimeCheckerLinuxVirmidi:
    """Tests for virmidi check on Linux."""

    def test_lsmod_not_found(self) -> None:
        runner = MockCommandRunner(
            {
                ("id", "-nG"): (0, "user dialout", ""),
            }
        )
        checker = RuntimeChecker(platform=Platform.LINUX, runner=runner)
        with patch("shutil.which", _which_factory({"id": "/usr/bin/id"})):
            results = checker.check_all()

        virmidi = next(r for r in results if r.name == "virmidi")
        assert virmidi.status == CheckStatus.WARNING
        assert "lsmod not found" in virmidi.message

    def test_virmidi_loaded(self) -> None:
        runner = MockCommandRunner(
            {
                ("lsmod",): (
                    0,
                    "Module                  Size  Used by\n"
                    "snd_virmidi            16384  0\n"
                    "snd_seq_dummy          16384  0",
                    "",
                ),
                ("id", "-nG"): (0, "user dialout", ""),
            }
        )
        checker = RuntimeChecker(platform=Platform.LINUX, runner=runner)
        with patch(
            "shutil.which", _which_factory({"lsmod": "/usr/sbin/lsmod", "id": "/usr/bin/id"})
        ):
            results = checker.check_all()

        virmidi = next(r for r in results if r.name == "virmidi")
        assert virmidi.status == CheckStatus.OK
        assert "loaded" in virmidi.message

    def test_virmidi_not_loaded(self) -> None:
        hints = Hints(runtime={"virmidi": {"linux": "sudo modprobe snd-virmidi"}})
        runner = MockCommandRunner(
            {
                ("lsmod",): (
                    0,
                    "Module                  Size  Used by\nsnd_seq_dummy          16384  0",
                    "",
                ),
                ("id", "-nG"): (0, "user dialout", ""),
            }
        )
        checker = RuntimeChecker(platform=Platform.LINUX, hints=hints, runner=runner)
        with patch(
            "shutil.which", _which_factory({"lsmod": "/usr/sbin/lsmod", "id": "/usr/bin/id"})
        ):
            results = checker.check_all()

        virmidi = next(r for r in results if r.name == "virmidi")
        assert virmidi.status == CheckStatus.WARNING
        assert virmidi.hint == "sudo modprobe snd-virmidi"


class TestRuntimeCheckerLinuxSerialPermissions:
    """Tests for serial permissions check on Linux."""

    def test_dialout_group(self) -> None:
        runner = MockCommandRunner(
            {
                ("lsmod",): (0, "snd_virmidi", ""),
                ("id", "-nG"): (0, "user dialout audio", ""),
            }
        )
        checker = RuntimeChecker(platform=Platform.LINUX, runner=runner)
        with patch(
            "shutil.which", _which_factory({"lsmod": "/usr/sbin/lsmod", "id": "/usr/bin/id"})
        ):
            results = checker.check_all()

        serial = next(r for r in results if r.name == "serial permissions")
        assert serial.status == CheckStatus.OK

    def test_uucp_group(self) -> None:
        runner = MockCommandRunner(
            {
                ("lsmod",): (0, "snd_virmidi", ""),
                ("id", "-nG"): (0, "user uucp wheel", ""),
            }
        )
        checker = RuntimeChecker(platform=Platform.LINUX, runner=runner)
        with patch(
            "shutil.which", _which_factory({"lsmod": "/usr/sbin/lsmod", "id": "/usr/bin/id"})
        ):
            results = checker.check_all()

        serial = next(r for r in results if r.name == "serial permissions")
        assert serial.status == CheckStatus.OK

    def test_udev_rules_exist(self) -> None:
        runner = MockCommandRunner(
            {
                ("lsmod",): (0, "snd_virmidi", ""),
                ("id", "-nG"): (0, "user audio wheel", ""),  # No dialout/uucp
            }
        )
        checker = RuntimeChecker(platform=Platform.LINUX, runner=runner)

        # Mock Path.exists for udev rules
        original_exists = Path.exists

        def mock_exists(path: Path) -> bool:
            if "teensy.rules" in str(path):
                return True
            return original_exists(path)

        with (
            patch(
                "shutil.which", _which_factory({"lsmod": "/usr/sbin/lsmod", "id": "/usr/bin/id"})
            ),
            patch.object(Path, "exists", mock_exists),
        ):
            results = checker.check_all()

        serial = next(r for r in results if r.name == "serial permissions")
        assert serial.status == CheckStatus.OK

    def test_no_permissions(self) -> None:
        runner = MockCommandRunner(
            {
                ("lsmod",): (0, "snd_virmidi", ""),
                ("id", "-nG"): (0, "user audio wheel", ""),
            }
        )
        checker = RuntimeChecker(platform=Platform.LINUX, runner=runner)
        with (
            patch(
                "shutil.which", _which_factory({"lsmod": "/usr/sbin/lsmod", "id": "/usr/bin/id"})
            ),
            patch.object(Path, "exists", return_value=False),
        ):
            results = checker.check_all()

        serial = next(r for r in results if r.name == "serial permissions")
        assert serial.status == CheckStatus.WARNING
        assert "ms bridge install" in (serial.hint or "")


class TestRuntimeCheckerMacOS:
    """Tests for macOS runtime checks."""

    def test_midi_recommendation(self) -> None:
        hints = Hints(runtime={"midi": {"macos": "Enable IAC Driver in Audio MIDI Setup"}})
        checker = RuntimeChecker(platform=Platform.MACOS, hints=hints)
        with patch("shutil.which", return_value=None):
            results = checker.check_all()

        midi = next(r for r in results if r.name == "MIDI")
        assert midi.status == CheckStatus.WARNING
        assert "IAC Driver" in midi.message


class TestRuntimeCheckerWindows:
    """Tests for Windows runtime checks."""

    def test_midi_recommendation(self) -> None:
        hints = Hints(runtime={"midi": {"windows": "Install loopMIDI: https://..."}})
        checker = RuntimeChecker(platform=Platform.WINDOWS, hints=hints)
        with patch("shutil.which", return_value=None):
            results = checker.check_all()

        midi = next(r for r in results if r.name == "MIDI")
        assert midi.status == CheckStatus.WARNING
        assert "loopMIDI" in midi.message


class TestRuntimeCheckerAssetTools:
    """Tests for optional asset tool checks."""

    def test_inkscape_installed(self) -> None:
        runner = MockCommandRunner(
            {
                ("inkscape", "--version"): (0, "Inkscape 1.3.2 (091e20e, 2023-11-25)", ""),
            }
        )
        checker = RuntimeChecker(platform=Platform.MACOS, runner=runner)
        with patch("shutil.which", _which_factory({"inkscape": "/usr/bin/inkscape"})):
            results = checker.check_all()

        inkscape = next(r for r in results if r.name == "inkscape")
        assert inkscape.status == CheckStatus.OK
        assert "1.3.2" in inkscape.message

    def test_fontforge_installed(self) -> None:
        runner = MockCommandRunner(
            {
                ("fontforge", "--version"): (0, "fontforge 20230101", ""),
            }
        )
        checker = RuntimeChecker(platform=Platform.MACOS, runner=runner)
        with patch("shutil.which", _which_factory({"fontforge": "/usr/bin/fontforge"})):
            results = checker.check_all()

        fontforge = next(r for r in results if r.name == "fontforge")
        assert fontforge.status == CheckStatus.OK
        assert "20230101" in fontforge.message

    def test_tools_not_installed(self) -> None:
        hints = Hints(
            tools={
                "inkscape": {"debian": "sudo apt install inkscape"},
                "fontforge": {"debian": "sudo apt install fontforge"},
            }
        )
        runner = MockCommandRunner(
            {
                ("lsmod",): (0, "snd_virmidi", ""),
                ("id", "-nG"): (0, "user dialout", ""),
            }
        )
        checker = RuntimeChecker(
            platform=Platform.LINUX,
            distro=LinuxDistro.DEBIAN,
            hints=hints,
            runner=runner,
        )
        with patch(
            "shutil.which", _which_factory({"lsmod": "/usr/sbin/lsmod", "id": "/usr/bin/id"})
        ):
            results = checker.check_all()

        inkscape = next(r for r in results if r.name == "inkscape")
        assert inkscape.status == CheckStatus.WARNING
        assert "optional" in inkscape.message
        assert inkscape.hint == "sudo apt install inkscape"

        fontforge = next(r for r in results if r.name == "fontforge")
        assert fontforge.status == CheckStatus.WARNING
        assert fontforge.hint == "sudo apt install fontforge"


class TestRuntimeCheckerCheckAll:
    """Tests for check_all method."""

    def test_linux_includes_asset_tools(self) -> None:
        runner = MockCommandRunner(
            {
                ("lsmod",): (0, "Module\nsnd_virmidi", ""),
                ("id", "-nG"): (0, "user dialout", ""),
            }
        )
        checker = RuntimeChecker(platform=Platform.LINUX, runner=runner)
        with patch(
            "shutil.which", _which_factory({"lsmod": "/usr/sbin/lsmod", "id": "/usr/bin/id"})
        ):
            results = checker.check_all()

        # Should have: virmidi, serial permissions, inkscape, fontforge
        names = [r.name for r in results]
        assert "virmidi" in names
        assert "serial permissions" in names
        assert "inkscape" in names
        assert "fontforge" in names

    def test_macos_includes_asset_tools(self) -> None:
        checker = RuntimeChecker(platform=Platform.MACOS)
        with patch("shutil.which", return_value=None):
            results = checker.check_all()

        names = [r.name for r in results]
        assert "MIDI" in names
        assert "inkscape" in names
        assert "fontforge" in names

    def test_windows_includes_asset_tools(self) -> None:
        checker = RuntimeChecker(platform=Platform.WINDOWS)
        with patch("shutil.which", return_value=None):
            results = checker.check_all()

        names = [r.name for r in results]
        assert "MIDI" in names
        assert "inkscape" in names
        assert "fontforge" in names

    def test_unknown_platform_only_asset_tools(self) -> None:
        checker = RuntimeChecker(platform=Platform.UNKNOWN)
        with patch("shutil.which", return_value=None):
            results = checker.check_all()

        names = [r.name for r in results]
        # Should only have asset tools, no platform-specific checks
        assert "inkscape" in names
        assert "fontforge" in names
        assert "virmidi" not in names
        assert "MIDI" not in names


class TestRuntimeCheckerFrozen:
    """Tests for dataclass immutability."""

    def test_frozen(self) -> None:
        checker = RuntimeChecker(platform=Platform.LINUX)
        with pytest.raises(AttributeError):
            checker.platform = Platform.WINDOWS  # type: ignore[misc]
