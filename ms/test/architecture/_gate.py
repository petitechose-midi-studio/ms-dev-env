from __future__ import annotations

import os

import pytest


def require_arch_checks_enabled() -> None:
    """Skip architecture checks unless explicitly enabled.

    Rationale: PR-A1 introduces advisory architecture checks first, then they can
    be turned into blocking checks once the migration reaches the target shape.
    """

    if os.getenv("MS_ARCH_CHECKS") != "1":
        pytest.skip(
            "architecture checks are advisory for now; set MS_ARCH_CHECKS=1 to enable",
        )
