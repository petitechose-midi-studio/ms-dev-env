from __future__ import annotations

import shutil
import tempfile
from pathlib import Path
from typing import Protocol


class _PytestOption(Protocol):
    basetemp: str | None


class _PytestConfig(Protocol):
    option: _PytestOption


_base_temp: Path | None = None


def pytest_configure(config: _PytestConfig) -> None:
    global _base_temp
    if config.option.basetemp is not None:
        return
    _base_temp = Path(tempfile.mkdtemp(prefix="ms-dev-env-pytest-"))
    config.option.basetemp = str(_base_temp)


def pytest_unconfigure(config: _PytestConfig) -> None:
    del config
    global _base_temp
    if _base_temp is None:
        return
    shutil.rmtree(_base_temp, ignore_errors=True)
    _base_temp = None
