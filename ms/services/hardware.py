"""Hardware build service.

Wraps the oc-* Python commands (oc-build, oc-upload, oc-monitor)
for Teensy firmware operations.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Literal

from ms.core.result import Err, Ok, Result
from ms.oc_cli.common import detect_env
from ms.output.console import Style
from ms.services.base import BaseService

if TYPE_CHECKING:
    from ms.core.app import App


__all__ = ["HardwareError", "HardwareService"]


@dataclass(frozen=True, slots=True)
class HardwareError:
    """Error from hardware operations."""

    kind: Literal["script_missing", "build_failed", "upload_failed", "no_platformio"]
    message: str
    hint: str | None = None


class HardwareService(BaseService):
    """Hardware builds using the oc-* Python commands."""

    def build(
        self,
        app: App,
        *,
        env: str | None = None,
        dry_run: bool = False,
    ) -> Result[None, HardwareError]:
        """Build firmware using oc-build."""
        if not app.has_teensy:
            return Err(HardwareError("no_platformio", f"no platformio.ini in {app.path}"))

        env_name = detect_env(app.path, env)
        result = self._run_oc("oc_build", app.path, "build", env=env_name, dry_run=dry_run)
        if isinstance(result, Err) or dry_run:
            return result

        return self._export_firmware(app.path, app_name=app.name, env_name=env_name)

    def upload(
        self,
        app: App,
        *,
        env: str | None = None,
        dry_run: bool = False,
    ) -> Result[None, HardwareError]:
        """Build and upload firmware using oc-upload."""
        if not app.has_teensy:
            return Err(HardwareError("no_platformio", f"no platformio.ini in {app.path}"))

        env_name = detect_env(app.path, env)
        result = self._run_oc("oc_upload", app.path, "upload", env=env_name, dry_run=dry_run)
        if isinstance(result, Err) or dry_run:
            return result

        return self._export_firmware(app.path, app_name=app.name, env_name=env_name)

    def monitor(self, app: App, *, env: str | None = None) -> int:
        """Build, upload, and monitor using oc-monitor."""
        if not app.has_teensy:
            self._console.error(f"no platformio.ini in {app.path}")
            return 1

        cmd = self._oc_cmd("oc_monitor", env=env)
        self._console.print(" ".join(cmd[:4]) + " ...", Style.DIM)

        # oc-monitor takes over the terminal
        env_vars = self._build_env()
        try:
            result = subprocess.run(
                cmd,
                cwd=app.path,
                env={**os.environ, **env_vars},
            )
            return result.returncode
        except KeyboardInterrupt:
            return 0

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

    def _oc_cmd(self, module: str, *, env: str | None) -> list[str]:
        cmd = [sys.executable, "-m", f"ms.oc_cli.{module}"]
        if env:
            cmd.append(env)
        return cmd

    def _run_oc(
        self,
        module: str,
        cwd: Path,
        action: str,
        *,
        env: str | None,
        dry_run: bool,
    ) -> Result[None, HardwareError]:
        """Run an oc-* python module."""
        cmd = self._oc_cmd(module, env=env)
        self._console.print(" ".join(cmd[:4]) + " ...", Style.DIM)

        if dry_run:
            return Ok(None)

        env_vars = self._build_env()
        try:
            result = subprocess.run(
                cmd,
                cwd=cwd,
                env={**os.environ, **env_vars},
            )
        except OSError as e:
            return Err(HardwareError("script_missing", str(e)))

        if result.returncode == 0:
            return Ok(None)
        return Err(
            HardwareError(
                f"{action}_failed",  # type: ignore[arg-type]
                f"{action} failed with code {result.returncode}",
            )
        )

    def _export_firmware(
        self, app_root: Path, *, app_name: str, env_name: str
    ) -> Result[None, HardwareError]:
        """Copy firmware.hex into bin/<app>/teensy/<env>/firmware.hex."""
        fw = app_root / ".pio" / "build" / env_name / "firmware.hex"
        if not fw.exists():
            return Err(
                HardwareError(
                    "build_failed",
                    f"firmware output missing: {fw}",
                    hint=f"Run: uv run ms build {app_name} --target teensy --env {env_name}",
                )
            )

        dst_dir = self._workspace.bin_dir / app_name / "teensy" / env_name
        dst_dir.mkdir(parents=True, exist_ok=True)
        try:
            shutil.copy2(fw, dst_dir / "firmware.hex")
        except OSError as e:
            return Err(HardwareError("build_failed", f"failed to export firmware: {e}"))

        return Ok(None)
