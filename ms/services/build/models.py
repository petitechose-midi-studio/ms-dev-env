from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

Target = Literal["native", "wasm"]


@dataclass(frozen=True, slots=True)
class AppConfig:
    app_id: str
    exe_name: str


_CMAKE_SET_RE = re.compile(r"^\s*set\(\s*(?P<name>[A-Z0-9_]+)\s+\"(?P<value>[^\"]+)\"\s*\)\s*$")


def extract_cmake_var(content: str, name: str) -> str | None:
    for line in content.splitlines():
        match = _CMAKE_SET_RE.match(line)
        if not match:
            continue
        if match.group("name") == name:
            return match.group("value")
    return None
