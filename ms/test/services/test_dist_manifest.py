from __future__ import annotations

import json
from pathlib import Path
from typing import cast

from ms.services.dist import generate_manifest, read_manifest


def test_generate_manifest_includes_assets_and_repos_lock(tmp_path: Path) -> None:
    # Minimal workspace layout
    (tmp_path / ".ms").mkdir()
    (tmp_path / "dist").mkdir()

    (tmp_path / ".ms" / "repos.lock.json").write_text(
        json.dumps(
            [
                {
                    "org": "open-control",
                    "name": "bridge",
                    "url": "https://example.invalid/open-control/bridge",
                    "default_branch": "main",
                    "head_sha": "0" * 40,
                }
            ]
        ),
        encoding="utf-8",
    )

    # Create fake dist zip
    zip_path = tmp_path / "dist" / "midi-studio-windows-x86_64-native.zip"
    zip_path.write_bytes(b"fakezip")

    out_path = generate_manifest(
        workspace_root=tmp_path,
        dist_dir=tmp_path / "dist",
        channel="beta",
        tag="v0.1.0-beta.1",
        out_path=tmp_path / "dist" / "manifest.json",
    )

    m = read_manifest(out_path)
    assert m["schema"] == 1
    assert m["channel"] == "beta"
    assert m["tag"] == "v0.1.0-beta.1"
    assert isinstance(m["source_hash"], str)

    repos = cast(list[dict[str, object]], m["repos"])
    assert cast(str, repos[0]["name"]) == "bridge"

    assets = cast(list[dict[str, object]], m["assets"])
    assert len(assets) == 1

    a = assets[0]
    assert cast(str, a["id"]) == "bundle_native_windows_x86_64"
    assert cast(str, a["filename"]) == "midi-studio-windows-x86_64-native.zip"
    assert cast(str, a["kind"]) == "bundle_native"
    assert cast(str, a["os"]) == "windows"
    assert cast(str, a["arch"]) == "x86_64"
    assert cast(int, a["size"]) == len(b"fakezip")
    assert isinstance(a["sha256"], str)
