from __future__ import annotations

import shutil
from pathlib import Path

from ms.core.result import Err, Ok, Result

from ._context import HardwareContextBase
from .models import HardwareError


class HardwareExporterMixin(HardwareContextBase):
    def _export_firmware(
        self,
        app_root: Path,
        *,
        app_name: str,
        env_name: str,
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
        except OSError as error:
            return Err(HardwareError("build_failed", f"failed to export firmware: {error}"))

        return Ok(None)
