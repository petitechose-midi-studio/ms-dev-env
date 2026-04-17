from __future__ import annotations

import json
from pathlib import Path

from ms.core.result import Err, Ok
from ms.release.infra.artifacts.app_version_writer import apply_version, current_version


def _seed_app_repo(tmp_path: Path, *, version: str, cargo_lock_version: str | None = None) -> Path:
    app_root = tmp_path / "ms-manager"
    src_tauri = app_root / "src-tauri"
    src_tauri.mkdir(parents=True)

    (app_root / "package.json").write_text(
        json.dumps({"name": "ms-manager", "version": version}, indent=2) + "\n",
        encoding="utf-8",
    )
    (src_tauri / "tauri.conf.json").write_text(
        json.dumps({"productName": "ms-manager", "version": version}, indent=2) + "\n",
        encoding="utf-8",
    )
    (src_tauri / "Cargo.toml").write_text(
        f"[package]\nname = \"ms-manager\"\nversion = \"{version}\"\n",
        encoding="utf-8",
    )
    (src_tauri / "Cargo.lock").write_text(
        "[[package]]\n"
        'name = "ms-manager"\n'
        f'version = "{cargo_lock_version or version}"\n',
        encoding="utf-8",
    )

    return app_root


def test_current_version_requires_cargo_lock_to_match(tmp_path: Path) -> None:
    app_root = _seed_app_repo(tmp_path, version="0.1.2-beta.1", cargo_lock_version="0.1.1")

    current = current_version(app_repo_root=app_root)

    assert isinstance(current, Err)
    assert current.error.kind == "invalid_input"
    assert "Cargo.lock=0.1.1" in (current.error.hint or "")


def test_apply_version_updates_cargo_lock(tmp_path: Path) -> None:
    app_root = _seed_app_repo(tmp_path, version="0.1.1")

    updated = apply_version(app_repo_root=app_root, version="0.1.2-beta.1")

    assert isinstance(updated, Ok)
    changed = {path.name for path in updated.value}
    assert changed == {"package.json", "Cargo.toml", "Cargo.lock", "tauri.conf.json"}
    cargo_lock_text = (app_root / "src-tauri" / "Cargo.lock").read_text(encoding="utf-8")
    assert 'version = "0.1.2-beta.1"' in cargo_lock_text
