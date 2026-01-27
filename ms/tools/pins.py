from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ms.core.structured import as_str_dict, get_str


@dataclass(frozen=True, slots=True)
class ToolPins:
    """Pinned tool versions (DEV).

    Values are tool-id -> version string.
    Special values:
    - "latest": resolve via tool.latest_version()
    - For JDK: can be "latest" (uses default major) or a major version like "25"
    """

    versions: dict[str, str]
    platformio_version: str

    @property
    def jdk_major(self) -> int | None:
        """Return JDK major version, or None for latest LTS default."""
        jdk = self.versions.get("jdk", "latest")
        if jdk == "latest":
            return None
        try:
            return int(jdk)
        except ValueError:
            return None

    @classmethod
    def load(cls, path: Path) -> ToolPins:
        import tomllib

        with path.open("rb") as f:
            data: dict[str, Any] = tomllib.load(f)

        versions: dict[str, str] = {}
        tools = data.get("tools")
        tools_map = as_str_dict(tools)
        if tools_map is not None:
            for k, v in tools_map.items():
                if isinstance(v, str):
                    versions[k] = v

        platformio_version = ""
        platformio = data.get("platformio")
        platformio_map = as_str_dict(platformio)
        if platformio_map is not None:
            pv = get_str(platformio_map, "version")
            if pv:
                platformio_version = pv

        if not platformio_version:
            raise ValueError("Missing [platformio].version in toolchains.toml")

        return cls(versions=versions, platformio_version=platformio_version)
