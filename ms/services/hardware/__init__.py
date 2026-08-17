from __future__ import annotations

from ms.services.hardware.models import FirmwareProfile, HardwareError
from ms.services.hardware.service import HardwareService

# Keep attribute for monkeypatch compatibility in tests/users.
subprocess = __import__("subprocess")

__all__ = ["FirmwareProfile", "HardwareError", "HardwareService"]
