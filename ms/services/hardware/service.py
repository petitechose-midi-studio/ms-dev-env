from __future__ import annotations

import json
import subprocess
from typing import TYPE_CHECKING, cast

from ms.core.platformio_runtime import resolve_platformio_runtime
from ms.core.result import Err, Ok, Result
from ms.oc_cli.common import detect_env
from ms.services.base import BaseService

from .adapter import OCHardwareAdapterMixin
from .exporter import HardwareExporterMixin
from .models import FirmwareProfile, HardwareError

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

    def profiles(self, app: App) -> Result[list[FirmwareProfile], HardwareError]:
        if not app.has_teensy:
            return Err(HardwareError("no_platformio", f"no platformio.ini in {app.path}"))

        runtime = resolve_platformio_runtime(app.path)
        if isinstance(runtime, Err):
            return Err(
                HardwareError(
                    "profile_discovery_failed",
                    runtime.error.message,
                    hint=runtime.error.hint,
                )
            )

        try:
            completed = subprocess.run(
                runtime.value.command("project", "config", "--json-output"),
                cwd=app.path,
                env=runtime.value.env,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
        except OSError as error:
            return Err(HardwareError("profile_discovery_failed", str(error)))

        if completed.returncode != 0:
            detail = completed.stderr.strip() or completed.stdout.strip()
            return Err(
                HardwareError(
                    "profile_discovery_failed",
                    detail or f"PlatformIO config failed with code {completed.returncode}",
                )
            )

        try:
            return Ok(_parse_profiles(completed.stdout))
        except (json.JSONDecodeError, ValueError) as error:
            return Err(HardwareError("profile_discovery_failed", str(error)))

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


def _parse_profiles(raw: str) -> list[FirmwareProfile]:
    config: object = json.loads(raw)
    if not isinstance(config, list):
        raise ValueError("PlatformIO config output is not a section list")

    profiles: list[FirmwareProfile] = []
    for section in cast(list[object], config):
        section_pair = _pair(section)
        if section_pair is None or not section_pair[0].startswith("env:"):
            continue

        env_name = section_pair[0].removeprefix("env:")
        options = dict(_pairs(section_pair[1]))
        if options.get("custom_ms_manager_profile") != env_name:
            continue

        profiles.append(FirmwareProfile(id=env_name))

    return profiles


def _pairs(value: object) -> list[tuple[str, object]]:
    if not isinstance(value, list):
        return []
    return [pair for item in cast(list[object], value) if (pair := _pair(item)) is not None]


def _pair(value: object) -> tuple[str, object] | None:
    if not isinstance(value, list):
        return None
    items = cast(list[object], value)
    if len(items) != 2 or not isinstance(items[0], str):
        return None
    return items[0], items[1]
