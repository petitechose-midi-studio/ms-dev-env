from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

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
    checksums: dict[str, str]

    def checksum_for(self, *, tool_id: str, version: str, platform: str, arch: str) -> str | None:
        keys = (
            f"{tool_id}:{version}:{platform}:{arch}",
            f"{tool_id}:{version}:{platform}:*",
            f"{tool_id}:{version}:*:*",
        )
        for key in keys:
            value = self.checksums.get(key)
            if value is not None:
                return value
        return None

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
            data_obj: object = tomllib.load(f)

        data = as_str_dict(data_obj)
        if data is None:
            raise ValueError("Invalid toolchains.toml (expected a TOML table)")

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

        checksums: dict[str, str] = {}
        checksums_raw = data.get("checksums")
        checksums_map = as_str_dict(checksums_raw)
        if checksums_map is not None:
            for key, value in checksums_map.items():
                if not isinstance(value, str):
                    continue
                digest = value.strip().lower()
                if not _is_sha256(digest):
                    raise ValueError(
                        f"Invalid checksum for key {key!r}: expected 64-char SHA256 hex"
                    )
                checksums[key.strip()] = digest

        return cls(versions=versions, platformio_version=platformio_version, checksums=checksums)


def _is_sha256(value: str) -> bool:
    if len(value) != 64:
        return False
    return all(ch in "0123456789abcdef" for ch in value)
