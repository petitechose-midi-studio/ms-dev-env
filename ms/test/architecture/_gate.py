from __future__ import annotations

import os

import pytest


def require_arch_checks_enabled() -> None:
    """Skip architecture checks unless explicitly enabled.

    CI sets ``MS_ARCH_CHECKS=1`` so architecture tests are blocking in pull
    requests. Local runs can opt in the same way when needed.
    """

    if os.getenv("MS_ARCH_CHECKS") != "1":
        pytest.skip(
            "architecture checks disabled; set MS_ARCH_CHECKS=1 to enable",
        )
