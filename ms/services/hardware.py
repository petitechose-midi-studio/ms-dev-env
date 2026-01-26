"""Hardware build service using open-control CLI tools.

Wraps oc-build, oc-upload, oc-monitor scripts for Teensy firmware operations.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Literal

from ms.core.result import Err, Ok, Result
from ms.output.console import Style
from ms.services.base import BaseService

if TYPE_CHECKING:
    from ms.core.app import App


__all__ = ["HardwareError", "HardwareService"]

# Git Bash path on Windows (avoid WSL bash)
_GIT_BASH = Path("C:/Program Files/Git/usr/bin/bash.exe")


@dataclass(frozen=True, slots=True)
class HardwareError:
    """Error from hardware operations."""

    kind: Literal["script_missing", "build_failed", "upload_failed", "no_platformio"]
    message: str
    hint: str | None = None


class HardwareService(BaseService):
    """Hardware builds using open-control CLI tools."""

    def build(self, app: App, *, dry_run: bool = False) -> Result[None, HardwareError]:
        """Build firmware using oc-build."""
        if not app.has_teensy:
            return Err(
                HardwareError("no_platformio", f"no platformio.ini in {app.path}")
            )

        script = self._oc_script("oc-build")
        if script is None:
            return Err(
                HardwareError("script_missing", "oc-build not found", "Run: ms sync --repos")
            )

        return self._run_script(script, app.path, "build", dry_run=dry_run)

    def upload(self, app: App, *, dry_run: bool = False) -> Result[None, HardwareError]:
        """Build and upload firmware using oc-upload."""
        if not app.has_teensy:
            return Err(
                HardwareError("no_platformio", f"no platformio.ini in {app.path}")
            )

        script = self._oc_script("oc-upload")
        if script is None:
            return Err(
                HardwareError("script_missing", "oc-upload not found", "Run: ms sync --repos")
            )

        return self._run_script(script, app.path, "upload", dry_run=dry_run)

    def monitor(self, app: App) -> int:
        """Build, upload, and monitor using oc-monitor."""
        if not app.has_teensy:
            self._console.error(f"no platformio.ini in {app.path}")
            return 1

        script = self._oc_script("oc-monitor")
        if script is None:
            self._console.error("oc-monitor not found")
            return 1

        bash = self._bash_cmd()
        self._console.print(f"{bash} {script}", Style.DIM)

        # oc-monitor takes over the terminal and doesn't return
        env = self._build_env()
        try:
            result = subprocess.run(
                [bash, str(script)],
                cwd=app.path,
                env={**subprocess.os.environ, **env},  # type: ignore[attr-defined]
            )
            return result.returncode
        except KeyboardInterrupt:
            return 0

    def _oc_script(self, name: str) -> Path | None:
        """Get path to open-control CLI script."""
        script = self._workspace.open_control_dir / "cli-tools" / "bin" / name
        if script.exists():
            return script
        return None

    def _bash_cmd(self) -> str:
        """Get bash command - use Git Bash on Windows to avoid WSL."""
        if self._platform.platform.is_windows and _GIT_BASH.exists():
            return str(_GIT_BASH)
        return "bash"

    def _build_env(self) -> dict[str, str]:
        """Build environment with PIO path and platformio directories."""
        env = self._workspace.platformio_env_vars()
        # Set PIO to workspace platformio if installed
        pio_venv = self._workspace.tools_dir / "platformio" / "venv"
        if self._platform.platform.is_windows:
            pio_bin = pio_venv / "Scripts" / "pio.exe"
        else:
            pio_bin = pio_venv / "bin" / "pio"
        if pio_bin.exists():
            env["PIO"] = str(pio_bin)
        return env

    def _run_script(
        self, script: Path, cwd: Path, action: str, *, dry_run: bool
    ) -> Result[None, HardwareError]:
        """Run an oc-* script."""
        bash = self._bash_cmd()
        self._console.print(f"{bash} {script}", Style.DIM)

        if dry_run:
            return Ok(None)

        env = self._build_env()
        try:
            result = subprocess.run(
                [bash, str(script)],
                cwd=cwd,
                env={**subprocess.os.environ, **env},  # type: ignore[attr-defined]
            )
            match result.returncode:
                case 0:
                    return Ok(None)
                case code:
                    return Err(
                        HardwareError(
                            f"{action}_failed",  # type: ignore[arg-type]
                            f"{action} failed with code {code}",
                        )
                    )
        except FileNotFoundError:
            return Err(
                HardwareError("script_missing", "bash not found", "Install Git Bash")
            )
