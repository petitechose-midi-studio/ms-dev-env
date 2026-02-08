"""Shared utilities for oc-* Python commands."""

from __future__ import annotations

from ms.oc_cli.common.execution import run_with_spinner
from ms.oc_cli.common.models import OCContext, OCPlatform
from ms.oc_cli.common.output_parser import show_results
from ms.oc_cli.common.runtime import build_pio_env, detect_env, find_project_root, get_console
from ms.oc_cli.common.serial import kill_monitors, list_serial_ports, wait_for_serial_port

# Keep attribute for monkeypatch compatibility in tests/users.
subprocess = __import__("subprocess")

__all__ = [
    "OCContext",
    "OCPlatform",
    "build_pio_env",
    "detect_env",
    "find_project_root",
    "get_console",
    "kill_monitors",
    "list_serial_ports",
    "run_with_spinner",
    "show_results",
    "wait_for_serial_port",
]
