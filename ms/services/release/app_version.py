from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from ms.core.result import Err, Ok, Result
from ms.core.structured import as_str_dict, get_str
from ms.platform.files import atomic_write_text
from ms.services.release.errors import ReleaseError


@dataclass(frozen=True, slots=True)
class AppVersionFiles:
    package_json: Path
    cargo_toml: Path
    tauri_conf: Path


def version_from_tag(*, tag: str) -> Result[str, ReleaseError]:
    if not tag.startswith("v") or len(tag) < 2:
        return Err(
            ReleaseError(
                kind="invalid_tag",
                message=f"invalid app tag: {tag}",
                hint="Expected vMAJOR.MINOR.PATCH[-beta.N]",
            )
        )
    return Ok(tag[1:])


def app_version_files(*, app_repo_root: Path) -> AppVersionFiles:
    return AppVersionFiles(
        package_json=app_repo_root / "package.json",
        cargo_toml=app_repo_root / "src-tauri" / "Cargo.toml",
        tauri_conf=app_repo_root / "src-tauri" / "tauri.conf.json",
    )


def current_version(*, app_repo_root: Path) -> Result[str, ReleaseError]:
    files = app_version_files(app_repo_root=app_repo_root)
    pkg_v = _read_json_version(path=files.package_json)
    if isinstance(pkg_v, Err):
        return pkg_v
    cargo_v = _read_cargo_package_version(path=files.cargo_toml)
    if isinstance(cargo_v, Err):
        return cargo_v
    tauri_v = _read_json_version(path=files.tauri_conf)
    if isinstance(tauri_v, Err):
        return tauri_v

    values = {pkg_v.value, cargo_v.value, tauri_v.value}
    if len(values) != 1:
        return Err(
            ReleaseError(
                kind="invalid_input",
                message="ms-manager version files are out of sync",
                hint=(
                    f"package.json={pkg_v.value}, Cargo.toml={cargo_v.value}, "
                    f"tauri.conf.json={tauri_v.value}"
                ),
            )
        )
    return Ok(pkg_v.value)


def apply_version(*, app_repo_root: Path, version: str) -> Result[list[Path], ReleaseError]:
    files = app_version_files(app_repo_root=app_repo_root)
    changed: list[Path] = []

    pkg = _write_json_version(path=files.package_json, version=version)
    if isinstance(pkg, Err):
        return pkg
    if pkg.value:
        changed.append(files.package_json)

    cargo = _write_cargo_package_version(path=files.cargo_toml, version=version)
    if isinstance(cargo, Err):
        return cargo
    if cargo.value:
        changed.append(files.cargo_toml)

    tauri = _write_json_version(path=files.tauri_conf, version=version)
    if isinstance(tauri, Err):
        return tauri
    if tauri.value:
        changed.append(files.tauri_conf)

    return Ok(changed)


def _read_json_version(*, path: Path) -> Result[str, ReleaseError]:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as e:
        return Err(
            ReleaseError(
                kind="dist_repo_failed",
                message=f"failed to read {path.name}: {e}",
                hint=str(path),
            )
        )

    try:
        obj: object = json.loads(text)
    except json.JSONDecodeError as e:
        return Err(
            ReleaseError(
                kind="invalid_input",
                message=f"invalid JSON in {path.name}: {e}",
                hint=str(path),
            )
        )

    data = as_str_dict(obj)
    if data is None:
        return Err(
            ReleaseError(
                kind="invalid_input",
                message=f"invalid JSON root in {path.name}",
                hint=str(path),
            )
        )

    value = get_str(data, "version")
    if value is None:
        return Err(
            ReleaseError(
                kind="invalid_input",
                message=f"missing version in {path.name}",
                hint=str(path),
            )
        )
    return Ok(value)


def _write_json_version(*, path: Path, version: str) -> Result[bool, ReleaseError]:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as e:
        return Err(
            ReleaseError(
                kind="dist_repo_failed",
                message=f"failed to read {path.name}: {e}",
                hint=str(path),
            )
        )

    try:
        obj: object = json.loads(text)
    except json.JSONDecodeError as e:
        return Err(
            ReleaseError(
                kind="invalid_input",
                message=f"invalid JSON in {path.name}: {e}",
                hint=str(path),
            )
        )

    data = as_str_dict(obj)
    if data is None:
        return Err(
            ReleaseError(
                kind="invalid_input",
                message=f"invalid JSON root in {path.name}",
                hint=str(path),
            )
        )

    prev = get_str(data, "version")
    if prev == version:
        return Ok(False)

    data["version"] = version

    try:
        atomic_write_text(path, json.dumps(data, indent=2) + "\n", encoding="utf-8")
    except OSError as e:
        return Err(
            ReleaseError(
                kind="dist_repo_failed",
                message=f"failed to write {path.name}: {e}",
                hint=str(path),
            )
        )

    return Ok(True)


def _read_cargo_package_version(*, path: Path) -> Result[str, ReleaseError]:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as e:
        return Err(
            ReleaseError(
                kind="dist_repo_failed",
                message=f"failed to read Cargo.toml: {e}",
                hint=str(path),
            )
        )

    pkg_idx = text.find("[package]")
    if pkg_idx < 0:
        return Err(
            ReleaseError(
                kind="invalid_input",
                message="missing [package] section in Cargo.toml",
                hint=str(path),
            )
        )

    sub = text[pkg_idx:]
    m = re.search(r'(?m)^version\s*=\s*"([^"]+)"\s*$', sub)
    if m is None:
        return Err(
            ReleaseError(
                kind="invalid_input",
                message="missing package version in Cargo.toml",
                hint=str(path),
            )
        )

    return Ok(m.group(1))


def _write_cargo_package_version(*, path: Path, version: str) -> Result[bool, ReleaseError]:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as e:
        return Err(
            ReleaseError(
                kind="dist_repo_failed",
                message=f"failed to read Cargo.toml: {e}",
                hint=str(path),
            )
        )

    pkg_idx = text.find("[package]")
    if pkg_idx < 0:
        return Err(
            ReleaseError(
                kind="invalid_input",
                message="missing [package] section in Cargo.toml",
                hint=str(path),
            )
        )

    prefix = text[:pkg_idx]
    sub = text[pkg_idx:]
    m = re.search(r'(?m)^version\s*=\s*"([^"]+)"\s*$', sub)
    if m is None:
        return Err(
            ReleaseError(
                kind="invalid_input",
                message="missing package version in Cargo.toml",
                hint=str(path),
            )
        )

    prev = m.group(1)
    if prev == version:
        return Ok(False)

    start = m.start()
    end = m.end()
    replaced = sub[:start] + f'version = "{version}"' + sub[end:]
    out = prefix + replaced

    try:
        atomic_write_text(path, out, encoding="utf-8")
    except OSError as e:
        return Err(
            ReleaseError(
                kind="dist_repo_failed",
                message=f"failed to write Cargo.toml: {e}",
                hint=str(path),
            )
        )

    return Ok(True)
