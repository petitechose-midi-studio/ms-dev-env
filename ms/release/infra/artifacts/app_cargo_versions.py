from __future__ import annotations

import re
from pathlib import Path

from ms.core.result import Err, Ok, Result
from ms.platform.files import atomic_write_text
from ms.release.errors import ReleaseError


def read_cargo_package_version(*, path: Path) -> Result[str, ReleaseError]:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as e:
        return Err(
            ReleaseError(
                kind="repo_failed",
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
    match = re.search(r'(?m)^version\s*=\s*"([^"]+)"\s*$', sub)
    if match is None:
        return Err(
            ReleaseError(
                kind="invalid_input",
                message="missing package version in Cargo.toml",
                hint=str(path),
            )
        )

    return Ok(match.group(1))


def write_cargo_package_version(*, path: Path, version: str) -> Result[bool, ReleaseError]:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as e:
        return Err(
            ReleaseError(
                kind="repo_failed",
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
    match = re.search(r'(?m)^version\s*=\s*"([^"]+)"\s*$', sub)
    if match is None:
        return Err(
            ReleaseError(
                kind="invalid_input",
                message="missing package version in Cargo.toml",
                hint=str(path),
            )
        )

    prev = match.group(1)
    if prev == version:
        return Ok(False)

    replaced = sub[: match.start()] + f'version = "{version}"' + sub[match.end() :]

    try:
        atomic_write_text(path, prefix + replaced, encoding="utf-8")
    except OSError as e:
        return Err(
            ReleaseError(
                kind="repo_failed",
                message=f"failed to write Cargo.toml: {e}",
                hint=str(path),
            )
        )

    return Ok(True)


def read_cargo_lock_package_version(*, path: Path) -> Result[str, ReleaseError]:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as e:
        return Err(
            ReleaseError(
                kind="repo_failed",
                message=f"failed to read Cargo.lock: {e}",
                hint=str(path),
            )
        )

    match = re.search(r'\[\[package\]\]\r?\nname = "ms-manager"\r?\nversion = "([^"]+)"', text)
    if match is None:
        return Err(
            ReleaseError(
                kind="invalid_input",
                message='missing root "ms-manager" package version in Cargo.lock',
                hint=str(path),
            )
        )

    return Ok(match.group(1))


def write_cargo_lock_package_version(*, path: Path, version: str) -> Result[bool, ReleaseError]:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as e:
        return Err(
            ReleaseError(
                kind="repo_failed",
                message=f"failed to read Cargo.lock: {e}",
                hint=str(path),
            )
        )

    match = re.search(r'\[\[package\]\]\r?\nname = "ms-manager"\r?\nversion = "([^"]+)"', text)
    if match is None:
        return Err(
            ReleaseError(
                kind="invalid_input",
                message='missing root "ms-manager" package version in Cargo.lock',
                hint=str(path),
            )
        )

    prev = match.group(1)
    if prev == version:
        return Ok(False)

    updated = text[: match.start(1)] + version + text[match.end(1) :]

    try:
        atomic_write_text(path, updated, encoding="utf-8")
    except OSError as e:
        return Err(
            ReleaseError(
                kind="repo_failed",
                message=f"failed to write Cargo.lock: {e}",
                hint=str(path),
            )
        )

    return Ok(True)
