from __future__ import annotations

from typing import TYPE_CHECKING

from ms.core.result import Err, Result
from ms.oc_cli.common import detect_env
from ms.services.base import BaseService

from .adapter import OCHardwareAdapterMixin
from .exporter import HardwareExporterMixin
from .models import HardwareError

if TYPE_CHECKING:
    from ms.core.app import App


class HardwareService(BaseService, OCHardwareAdapterMixin, HardwareExporterMixin):
    """Hardware builds using the oc-* Python commands."""

    def build(
        self,
        app: App,
        *,
        env: str | None = None,
        dry_run: bool = False,
    ) -> Result[None, HardwareError]:
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
        if not app.has_teensy:
            return Err(HardwareError("no_platformio", f"no platformio.ini in {app.path}"))

        env_name = detect_env(app.path, env)
        result = self._run_oc("oc_upload", app.path, "upload", env=env_name, dry_run=dry_run)
        if isinstance(result, Err) or dry_run:
            return result

        return self._export_firmware(app.path, app_name=app.name, env_name=env_name)

    def monitor(self, app: App, *, env: str | None = None) -> int:
        if not app.has_teensy:
            self._console.error(f"no platformio.ini in {app.path}")
            return 1
        return self._run_monitor(app.path, env=env)
