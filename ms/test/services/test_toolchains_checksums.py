from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from ms.core.workspace import Workspace
from ms.output.console import MockConsole
from ms.platform.detection import Arch, LinuxDistro, Platform, PlatformInfo
from ms.services.toolchains import ToolchainService, sha256_file
from ms.tools.pins import ToolPins


def _service(tmp_path: Path, console: MockConsole) -> ToolchainService:
    return ToolchainService(
        workspace=Workspace(root=tmp_path),
        platform=PlatformInfo(platform=Platform.LINUX, arch=Arch.X64, distro=LinuxDistro.UNKNOWN),
        config=None,
        console=console,
    )


def test_sha256_file_matches_hashlib(tmp_path: Path) -> None:
    file_path = tmp_path / "archive.tar.gz"
    file_path.write_bytes(b"checksum-test-bytes")

    expected = hashlib.sha256(b"checksum-test-bytes").hexdigest()
    assert sha256_file(file_path) == expected


def test_verify_download_checksum_accepts_exact_match(tmp_path: Path) -> None:
    console = MockConsole()
    service = _service(tmp_path, console)
    archive = tmp_path / "tool.zip"
    archive.write_bytes(b"hello")
    digest = hashlib.sha256(b"hello").hexdigest()
    pins = ToolPins(
        versions={"cmake": "4.2.2"},
        platformio_version="6.1.18",
        checksums={"cmake:4.2.2:linux:x64": digest},
    )

    ok = service.verify_download_checksum(
        tool_id="cmake",
        version="4.2.2",
        archive_path=archive,
        pins=pins,
    )
    assert ok is True
    assert "cmake: checksum verified" in console.text


def test_verify_download_checksum_rejects_mismatch(tmp_path: Path) -> None:
    console = MockConsole()
    service = _service(tmp_path, console)
    archive = tmp_path / "tool.zip"
    archive.write_bytes(b"actual")
    pins = ToolPins(
        versions={"cmake": "4.2.2"},
        platformio_version="6.1.18",
        checksums={"cmake:4.2.2:linux:x64": "0" * 64},
    )

    ok = service.verify_download_checksum(
        tool_id="cmake",
        version="4.2.2",
        archive_path=archive,
        pins=pins,
    )
    assert ok is False
    assert "cmake: checksum verification failed" in console.text


def test_toolpins_checksum_for_wildcard_fallback() -> None:
    pins = ToolPins(
        versions={},
        platformio_version="6.1.18",
        checksums={"cmake:4.2.2:*:*": "a" * 64},
    )
    assert (
        pins.checksum_for(tool_id="cmake", version="4.2.2", platform="linux", arch="x64")
        == "a" * 64
    )


def test_toolpins_load_rejects_invalid_checksum(tmp_path: Path) -> None:
    pins_file = tmp_path / "toolchains.toml"
    pins_file.write_text(
        """
[tools]
cmake = "4.2.2"

[platformio]
version = "6.1.18"

[checksums]
"cmake:4.2.2:linux:x64" = "not-a-sha"
""".strip(),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="Invalid checksum"):
        ToolPins.load(pins_file)
