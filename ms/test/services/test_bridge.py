from __future__ import annotations

# pyright: reportPrivateUsage=false
import hashlib
from pathlib import Path

from ms.core.result import Err, Ok
from ms.services.bridge import (
    _load_bridge_checksums,
    _resolve_release_tag,
    _verify_prebuilt_checksum,
)
from ms.tools.http import HttpError, MockHttpClient


def test_verify_prebuilt_checksum_ok(tmp_path: Path) -> None:
    downloaded = tmp_path / "oc-bridge-linux"
    downloaded.write_bytes(b"bridge-bin")
    digest = hashlib.sha256(b"bridge-bin").hexdigest()

    result = _verify_prebuilt_checksum(
        checksums={"v1.2.3:oc-bridge-linux": digest},
        release_tag="v1.2.3",
        asset="oc-bridge-linux",
        downloaded_path=downloaded,
        strict=True,
    )

    assert isinstance(result, Ok)


def test_verify_prebuilt_checksum_mismatch_fails(tmp_path: Path) -> None:
    downloaded = tmp_path / "oc-bridge-linux"
    downloaded.write_bytes(b"actual")

    result = _verify_prebuilt_checksum(
        checksums={"v1.2.3:oc-bridge-linux": "0" * 64},
        release_tag="v1.2.3",
        asset="oc-bridge-linux",
        downloaded_path=downloaded,
        strict=True,
    )

    assert isinstance(result, Err)
    assert result.error.kind == "checksum_mismatch"


def test_verify_prebuilt_checksum_missing_fails_in_strict_mode(tmp_path: Path) -> None:
    downloaded = tmp_path / "oc-bridge-linux"
    downloaded.write_bytes(b"actual")

    result = _verify_prebuilt_checksum(
        checksums={},
        release_tag="v1.2.3",
        asset="oc-bridge-linux",
        downloaded_path=downloaded,
        strict=True,
    )

    assert isinstance(result, Err)
    assert result.error.kind == "checksum_missing"


def test_resolve_release_tag_uses_latest_metadata_when_version_unspecified() -> None:
    http = MockHttpClient()
    http.set_json(
        "https://api.github.com/repos/open-control/bridge/releases/latest",
        {"tag_name": "v9.9.9"},
    )

    result = _resolve_release_tag(version=None, http=http)

    assert isinstance(result, Ok)
    assert result.value == "v9.9.9"


def test_resolve_release_tag_returns_error_on_http_failure() -> None:
    http = MockHttpClient()
    http.set_json(
        "https://api.github.com/repos/open-control/bridge/releases/latest",
        HttpError(url="https://api.github.com", status=503, message="unavailable"),
    )

    result = _resolve_release_tag(version=None, http=http)

    assert isinstance(result, Err)
    assert result.error.kind == "release_metadata_failed"


def test_load_bridge_checksums_rejects_invalid_digest(tmp_path: Path) -> None:
    checksums_file = tmp_path / "bridge_checksums.toml"
    checksums_file.write_text(
        """
schema = 1

[checksums]
"v1.0.0:oc-bridge-linux" = "bad"
""".strip(),
        encoding="utf-8",
    )

    result = _load_bridge_checksums(path=checksums_file)

    assert isinstance(result, Err)
    assert result.error.kind == "checksum_manifest_invalid"
