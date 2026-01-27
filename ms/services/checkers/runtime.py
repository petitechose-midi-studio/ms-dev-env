# SPDX-License-Identifier: MIT
"""Runtime environment checker.

Validates runtime requirements:
- Linux: virmidi module, serial permissions (dialout/uucp), udev rules
- macOS: IAC Driver recommendation
- Windows: loopMIDI recommendation
- All: Optional asset tools (inkscape, fontforge)
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from ms.services.checkers.base import CheckResult
from ms.services.checkers.common import (
    CommandRunner,
    DefaultCommandRunner,
    Hints,
    first_line,
    get_platform_key,
)

if TYPE_CHECKING:
    from ms.platform.detection import LinuxDistro, Platform


@dataclass(frozen=True, slots=True)
class RuntimeChecker:
    """Check runtime environment.

    Attributes:
        platform: Current platform
        distro: Linux distribution (for hint lookup)
        hints: Runtime hints
        runner: Command runner for checks
    """

    platform: "Platform"
    distro: "LinuxDistro | None" = None
    hints: Hints = field(default_factory=Hints.empty)
    runner: CommandRunner = field(default_factory=DefaultCommandRunner)

    def check_all(self) -> list[CheckResult]:
        """Run all runtime checks."""
        from ms.platform.detection import Platform

        results: list[CheckResult] = []

        match self.platform:
            case Platform.LINUX:
                results.extend(self._check_linux())
            case Platform.MACOS:
                results.extend(self._check_macos())
            case Platform.WINDOWS:
                results.extend(self._check_windows())
            case _:
                pass

        # Asset tools (optional on all platforms)
        results.extend(self._check_asset_tools())

        return results

    def _check_linux(self) -> list[CheckResult]:
        """Check Linux runtime requirements."""
        return [
            self._check_virmidi(),
            self._check_serial_permissions(),
        ]

    def _check_virmidi(self) -> CheckResult:
        """Check if snd-virmidi kernel module is loaded."""
        lsmod = shutil.which("lsmod")
        if not lsmod:
            return CheckResult.warning("virmidi", "cannot check (lsmod not found)")

        try:
            result = self.runner.run(["lsmod"])
            if result.returncode == 0 and "snd_virmidi" in result.stdout:
                return CheckResult.success("virmidi", "loaded")
            return CheckResult.warning(
                "virmidi",
                "not loaded",
                hint=self.hints.get_runtime_hint("virmidi", "linux"),
            )
        except Exception:
            return CheckResult.warning("virmidi", "check failed")

    def _check_serial_permissions(self) -> CheckResult:
        """Check serial port permissions."""
        groups_ok = False
        id_cmd = shutil.which("id")
        if id_cmd:
            try:
                result = self.runner.run(["id", "-nG"])
                if result.returncode == 0:
                    groups = set(result.stdout.split())
                    groups_ok = bool(groups.intersection({"dialout", "uucp"}))
            except Exception:
                pass

        udev_candidates = [
            Path("/etc/udev/rules.d/49-oc-bridge.rules"),
            Path("/etc/udev/rules.d/00-teensy.rules"),
            Path("/etc/udev/rules.d/99-platformio-udev.rules"),
        ]
        udev_ok = any(p.exists() for p in udev_candidates)

        if groups_ok or udev_ok:
            return CheckResult.success("serial permissions", "ok")

        return CheckResult.warning(
            "serial permissions",
            "missing",
            hint="Run: uv run ms bridge install (or see docs for manual setup)",
        )

    def _check_macos(self) -> list[CheckResult]:
        """Check macOS runtime requirements."""
        return [
            CheckResult.warning(
                "MIDI",
                "configure IAC Driver in Audio MIDI Setup",
                hint=self.hints.get_runtime_hint("midi", "macos"),
            )
        ]

    def _check_windows(self) -> list[CheckResult]:
        """Check Windows runtime requirements."""
        return [
            CheckResult.warning(
                "MIDI",
                "install loopMIDI for virtual MIDI ports",
                hint=self.hints.get_runtime_hint("midi", "windows"),
            )
        ]

    def _check_asset_tools(self) -> list[CheckResult]:
        """Check optional asset generation tools."""
        results: list[CheckResult] = []

        # Inkscape
        if shutil.which("inkscape"):
            results.append(self._check_tool_version("inkscape", ["--version"]))
        else:
            results.append(
                CheckResult.warning(
                    "inkscape",
                    "missing (optional)",
                    hint=self._get_tool_hint("inkscape"),
                )
            )

        # FontForge
        if shutil.which("fontforge"):
            results.append(self._check_tool_version("fontforge", ["--version"]))
        else:
            results.append(
                CheckResult.warning(
                    "fontforge",
                    "missing (optional)",
                    hint=self._get_tool_hint("fontforge"),
                )
            )

        return results

    def _check_tool_version(self, name: str, version_args: list[str]) -> CheckResult:
        """Check tool and get version."""
        try:
            result = self.runner.run([name, *version_args])
            if result.returncode == 0:
                version = first_line(result.stdout + result.stderr)
                return CheckResult.success(name, version if version else "ok")
        except Exception:
            pass
        return CheckResult.success(name, "ok")

    def _get_tool_hint(self, tool_id: str) -> str | None:
        """Get installation hint for a tool."""
        platform_key = get_platform_key(self.platform, self.distro)
        return self.hints.get_tool_hint(tool_id, platform_key)
