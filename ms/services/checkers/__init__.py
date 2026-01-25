# SPDX-License-Identifier: MIT
"""Checker modules for environment validation.

Each checker is responsible for a specific domain:
- WorkspaceChecker: Validates workspace structure (repos, config)
- ToolsChecker: Validates tools installation
- SystemChecker: Validates system dependencies (SDL2, ALSA)
- RuntimeChecker: Validates runtime environment (virmidi, serial)
"""

from ms.services.checkers.base import CheckResult, CheckStatus
from ms.services.checkers.common import Hints, load_hints
from ms.services.checkers.runtime import RuntimeChecker
from ms.services.checkers.system import SystemChecker
from ms.services.checkers.tools import ToolsChecker
from ms.services.checkers.workspace import WorkspaceChecker

__all__ = [
    # Result types
    "CheckResult",
    "CheckStatus",
    # Hints
    "Hints",
    "load_hints",
    # Checkers
    "WorkspaceChecker",
    "ToolsChecker",
    "SystemChecker",
    "RuntimeChecker",
]
