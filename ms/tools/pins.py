from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast


@dataclass(frozen=True, slots=True)
class ToolPins:
    """Pinned tool versions (DEV).

    Values are tool-id -> version string.
    Special values:
    - "latest": resolve via tool.latest_version()
    """

    versions: dict[str, str]
    platformio_version: str

    @classmethod
    def load(cls, path: Path) -> ToolPins:
        import tomllib

        with path.open("rb") as f:
            data: dict[str, Any] = tomllib.load(f)

        versions: dict[str, str] = {}
        tools = data.get("tools")
        if isinstance(tools, dict):
            tools_map = cast(dict[str, Any], tools)
            for k, v in tools_map.items():
                if isinstance(v, str):
                    versions[k] = v

        platformio_version = ""
        platformio = data.get("platformio")
        if isinstance(platformio, dict):
            pv = cast(dict[str, Any], platformio).get("version")
            if isinstance(pv, str):
                platformio_version = pv

        if not platformio_version:
            raise ValueError("Missing [platformio].version in toolchains.toml")

        return cls(versions=versions, platformio_version=platformio_version)
