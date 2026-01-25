# SPDX-License-Identifier: MIT
"""System dependencies checker.

Validates system-level dependencies:
- Linux: SDL2, ALSA, pkg-config
- macOS: SDL2 (via brew)
- Windows: SDL2 (bundled)
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
    get_platform_key,
)

if TYPE_CHECKING:
    from ms.platform.detection import LinuxDistro, Platform


@dataclass(frozen=True, slots=True)
class SystemChecker:
    """Check system dependencies.

    Attributes:
        platform: Current platform
        distro: Linux distribution (if on Linux)
        tools_dir: Path to bundled tools directory
        hints: Installation hints
        runner: Command runner for checks
    """

    platform: "Platform"
    distro: "LinuxDistro | None" = None
    tools_dir: Path | None = None
    hints: Hints = field(default_factory=Hints.empty)
    runner: CommandRunner = field(default_factory=DefaultCommandRunner)

    def check_all(self) -> list[CheckResult]:
        """Run all system dependency checks."""
        from ms.platform.detection import Platform

        match self.platform:
            case Platform.LINUX:
                return self._check_linux()
            case Platform.MACOS:
                return self._check_macos()
            case Platform.WINDOWS:
                return self._check_windows()
            case _:
                return []

    def _check_linux(self) -> list[CheckResult]:
        """Check Linux system dependencies."""
        results: list[CheckResult] = []

        # pkg-config is required for SDL2/ALSA detection
        pkg_config = shutil.which("pkg-config")
        if not pkg_config:
            results.append(
                CheckResult.error(
                    "pkg-config",
                    "missing",
                    hint=self._get_system_hint("pkg-config"),
                )
            )
            results.append(CheckResult.warning("SDL2", "cannot check (pkg-config missing)"))
            results.append(CheckResult.warning("ALSA", "cannot check (pkg-config missing)"))
            return results

        results.append(CheckResult.success("pkg-config", "ok"))

        # Check SDL2
        sdl2_result = self.runner.run(["pkg-config", "--exists", "sdl2"])
        if sdl2_result.returncode == 0:
            version_result = self.runner.run(["pkg-config", "--modversion", "sdl2"])
            version = version_result.stdout.strip() if version_result.returncode == 0 else ""
            msg = f"ok ({version})" if version else "ok"
            results.append(CheckResult.success("SDL2", msg))
        else:
            results.append(CheckResult.error("SDL2", "missing", hint=self._get_system_hint("sdl2")))

        # Check ALSA
        alsa_result = self.runner.run(["pkg-config", "--exists", "alsa"])
        if alsa_result.returncode == 0:
            version_result = self.runner.run(["pkg-config", "--modversion", "alsa"])
            version = version_result.stdout.strip() if version_result.returncode == 0 else ""
            msg = f"ok ({version})" if version else "ok"
            results.append(CheckResult.success("ALSA", msg))
        else:
            results.append(CheckResult.error("ALSA", "missing", hint=self._get_system_hint("alsa")))

        return results

    def _check_macos(self) -> list[CheckResult]:
        """Check macOS system dependencies."""
        results: list[CheckResult] = []

        brew = shutil.which("brew")
        if not brew:
            results.append(
                CheckResult.error(
                    "brew",
                    "missing (required for SDL2)",
                    hint="Install from https://brew.sh",
                )
            )
            results.append(CheckResult.warning("SDL2", "cannot check (brew missing)"))
            return results

        results.append(CheckResult.success("brew", "ok"))

        sdl2_result = self.runner.run(["brew", "list", "sdl2"])
        if sdl2_result.returncode == 0:
            results.append(CheckResult.success("SDL2", "ok"))
        else:
            results.append(CheckResult.error("SDL2", "missing", hint=self._get_system_hint("sdl2")))

        return results

    def _check_windows(self) -> list[CheckResult]:
        """Check Windows system dependencies."""
        results: list[CheckResult] = []

        if self.tools_dir:
            sdl2_candidates = [
                self.tools_dir / "windows" / "SDL2",
                self.tools_dir / "sdl2",
                self.tools_dir / "SDL2",
                self.tools_dir / "sdl2" / "x86_64-w64-mingw32",
            ]
            sdl2_found = any(
                (p / "lib").is_dir()
                or (p / "include").is_dir()
                or (p / "bin" / "SDL2.dll").is_file()
                for p in sdl2_candidates
            )
            if sdl2_found:
                results.append(CheckResult.success("SDL2", "ok (bundled)"))
            else:
                results.append(
                    CheckResult.warning(
                        "SDL2",
                        "not found",
                        hint="Run: uv run ms tools sync",
                    )
                )
        else:
            results.append(CheckResult.warning("SDL2", "cannot check (tools_dir not set)"))

        return results

    def _get_system_hint(self, dep_id: str) -> str | None:
        """Get installation hint for a system dependency."""
        platform_key = get_platform_key(self.platform, self.distro)
        return self.hints.get_system_hint(dep_id, platform_key)
