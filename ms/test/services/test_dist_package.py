from __future__ import annotations

import os
from pathlib import Path

from ms.platform.detection import Platform, detect
from ms.services.dist import package_platform


def test_package_platform_handles_epoch_mtime(tmp_path: Path) -> None:
    # Minimal workspace structure
    (tmp_path / "bin" / "bridge").mkdir(parents=True)
    (tmp_path / "bin" / "core" / "native").mkdir(parents=True)
    (tmp_path / "bin" / "bitwig" / "native").mkdir(parents=True)
    (tmp_path / "dist").mkdir()

    # Create the per-platform uploader binary with an epoch mtime (1970), which
    # would normally break ZIP (timestamps before 1980 are invalid in ZIP).
    info = detect()
    loader_name = (
        "midi-studio-loader.exe" if info.platform == Platform.WINDOWS else "midi-studio-loader"
    )
    loader_dir = tmp_path / "midi-studio" / "loader" / "target" / "release"
    loader_dir.mkdir(parents=True)
    loader_bin = loader_dir / loader_name
    loader_bin.write_bytes(b"loader")
    os.utime(loader_bin, (0, 0))

    created = package_platform(
        workspace_root=tmp_path,
        out_dir=tmp_path / "dist",
        require_uploader=True,
    )

    # We should at least get the uploader bundle.
    assert any(p.name.endswith("-teensy-uploader.zip") for p in created)
