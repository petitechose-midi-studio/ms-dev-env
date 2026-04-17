from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from ms.core.result import Err, Ok, Result
from ms.output.console import Style

from ._context import HardwareContextBase
from .models import HardwareAction, HardwareError, failure_kind


class OCHardwareAdapterMixin(HardwareContextBase):
    def _build_env(self) -> dict[str, str]:
        return self._workspace.platformio_env_vars()

    def _oc_cmd(self, module: str, *, env: str | None) -> list[str]:
        cmd = [sys.executable, "-m", f"ms.oc_cli.{module}"]
        if env:
            cmd.append(env)
        return cmd

    def _run_oc(
        self,
        module: str,
        cwd: Path,
        action: HardwareAction,
        *,
        env: str | None,
        dry_run: bool,
    ) -> Result[None, HardwareError]:
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
        except OSError as error:
            return Err(HardwareError("script_missing", str(error)))

        if result.returncode == 0:
            return Ok(None)

        return Err(
            HardwareError(
                failure_kind(action),
                f"{action} failed with code {result.returncode}",
            )
        )

    def _run_monitor(self, app_path: Path, *, env: str | None) -> int:
        cmd = self._oc_cmd("oc_monitor", env=env)
        self._console.print(" ".join(cmd[:4]) + " ...", Style.DIM)

        env_vars = self._build_env()
        try:
            result = subprocess.run(
                cmd,
                cwd=app_path,
                env={**os.environ, **env_vars},
            )
            return result.returncode
        except KeyboardInterrupt:
            return 0
