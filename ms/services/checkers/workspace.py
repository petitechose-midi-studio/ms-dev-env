# SPDX-License-Identifier: MIT
"""Workspace structure checker.

Validates that the workspace has:
- open-control/ repository
- midi-studio/ repository
- config.toml (optional but recommended)
- emsdk/ directory
- oc-bridge binary (installed or built)
- bitwig host directory
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from ms.services.checkers.base import CheckResult

if TYPE_CHECKING:
    from ms.core.config import Config
    from ms.core.workspace import Workspace
    from ms.platform.detection import Platform


def _empty_bitwig_paths() -> dict[str, str]:
    """Factory for empty bitwig paths dict."""
    return {}


@dataclass(frozen=True, slots=True)
class WorkspaceChecker:
    """Check workspace structure and configuration.

    Attributes:
        workspace: The workspace to check
        platform: Current platform for platform-specific checks
        config: Optional loaded config (if config.toml exists and is valid)
        bitwig_paths: Platform-specific Bitwig paths from raw config
    """

    workspace: Workspace
    platform: Platform
    config: Config | None = None
    bitwig_paths: dict[str, str] = field(default_factory=_empty_bitwig_paths)

    def check_all(self) -> list[CheckResult]:
        """Run all workspace checks."""
        return [
            self.check_open_control(),
            self.check_midi_studio(),
            self.check_config(),
            self.check_emsdk(),
            self.check_bridge(),
            self.check_bitwig_host(),
            self.check_bitwig_extensions(),
        ]

    def check_open_control(self) -> CheckResult:
        """Check open-control/ repository exists."""
        path = self.workspace.root / "open-control"
        if path.is_dir():
            return CheckResult.success("open-control", "ok")
        return CheckResult.error(
            "open-control",
            "missing",
            hint="Run: uv run ms sync --repos",
        )

    def check_midi_studio(self) -> CheckResult:
        """Check midi-studio/ repository exists."""
        path = self.workspace.root / "midi-studio"
        if path.is_dir():
            return CheckResult.success("midi-studio", "ok")
        return CheckResult.error(
            "midi-studio",
            "missing",
            hint="Run: uv run ms sync --repos",
        )

    def check_config(self) -> CheckResult:
        """Check config.toml exists and is valid."""
        path = self.workspace.root / "config.toml"
        if not path.exists():
            return CheckResult.warning(
                "config.toml",
                "missing (using defaults)",
                hint="Copy config.example.toml to config.toml",
            )
        if self.config is not None:
            return CheckResult.success("config.toml", "ok")
        return CheckResult.warning("config.toml", "exists but not validated")

    def check_emsdk(self) -> CheckResult:
        """Check emsdk/ directory exists."""
        tools_dir = self._get_tools_dir()
        emsdk_dir = tools_dir / "emsdk"
        if (emsdk_dir / "emsdk.py").exists():
            return CheckResult.success("emsdk", "ok")
        return CheckResult.error(
            "emsdk",
            "missing",
            hint="Run: uv run ms sync --tools",
        )

    def check_bridge(self) -> CheckResult:
        """Check oc-bridge binary is installed or built."""
        bridge_dir = self._get_bridge_dir()
        exe_name = self._exe_name("oc-bridge")
        installed_bin = self.workspace.bin_dir / "bridge" / exe_name
        if installed_bin.exists():
            return CheckResult.success("oc-bridge", f"installed ({installed_bin})")

        bridge_bin = bridge_dir / "target" / "release" / exe_name
        if bridge_bin.exists():
            return CheckResult.success("oc-bridge", f"built ({bridge_bin})")
        return CheckResult.error(
            "oc-bridge",
            "missing",
            hint="Run: uv run ms bridge install",
        )

    def check_bitwig_host(self) -> CheckResult:
        """Check bitwig host directory exists with pom.xml."""
        ext_dir = self._get_extension_dir()
        if (ext_dir / "pom.xml").exists():
            return CheckResult.success("bitwig host", "ok")
        return CheckResult.error(
            "bitwig host",
            "missing",
            hint="Run: uv run ms sync --repos",
        )

    def check_bitwig_extensions(self) -> CheckResult:
        """Check Bitwig Extensions directory exists for deployment."""
        candidates = self._get_bitwig_extensions_candidates()
        resolved = next((p for p in candidates if p.exists()), None)
        if resolved is not None:
            return CheckResult.success("bitwig extensions", str(resolved))
        if candidates:
            return CheckResult.warning(
                "bitwig extensions",
                f"not found (expected: {candidates[0]})",
            )
        return CheckResult.warning("bitwig extensions", "not configured")

    def _get_tools_dir(self) -> Path:
        """Get tools directory from config or default."""
        if self.config is not None:
            return self.workspace.root / self.config.paths.tools
        return self.workspace.root / "tools"

    def _get_bridge_dir(self) -> Path:
        """Get bridge directory from config or default."""
        if self.config is not None:
            return self.workspace.root / self.config.paths.bridge
        return self.workspace.root / "open-control" / "bridge"

    def _get_extension_dir(self) -> Path:
        """Get extension directory from config or default."""
        if self.config is not None:
            return self.workspace.root / self.config.paths.extension
        return self.workspace.root / "midi-studio" / "plugin-bitwig" / "host"

    def _get_bitwig_extensions_candidates(self) -> list[Path]:
        """Get candidate paths for Bitwig Extensions directory."""
        from ms.platform.detection import Platform

        # Check config for platform-specific path
        platform_key = str(self.platform)
        if platform_key in self.bitwig_paths:
            configured = self.bitwig_paths[platform_key]
            if configured:
                return [Path(configured).expanduser()]

        # Platform-specific defaults
        home = Path.home()
        match self.platform:
            case Platform.LINUX:
                return [
                    home / "Bitwig Studio" / "Extensions",
                    home / ".BitwigStudio" / "Extensions",
                ]
            case Platform.MACOS | Platform.WINDOWS:
                return [home / "Documents" / "Bitwig Studio" / "Extensions"]
            case _:
                return []

    def _exe_name(self, name: str) -> str:
        """Get executable name for current platform."""
        if self.platform.is_windows:
            return f"{name}.exe"
        return name
