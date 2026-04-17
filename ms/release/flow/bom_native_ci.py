from __future__ import annotations

import configparser
from pathlib import Path

from ms.core.result import Err, Ok, Result
from ms.release.domain.open_control_models import (
    OPEN_CONTROL_NATIVE_CI_REPOS,
    DerivedBomLock,
    OcSdkPin,
)
from ms.release.errors import ReleaseError
from ms.release.infra.open_control import parse_open_control_git_pins
from ms.release.infra.open_control_writer import parse_native_ci_sdk_ini

_OC_NATIVE_SDK_FILE = "oc-native-sdk.ini"


def load_native_ci_bom(*, core_root: Path) -> Result[DerivedBomLock, ReleaseError]:
    derived_file = core_root / _OC_NATIVE_SDK_FILE
    if derived_file.exists():
        return _load_native_ci_bom_from_generated_file(path=derived_file)
    return _load_native_ci_bom_from_platformio(path=core_root / "platformio.ini")


def _load_native_ci_bom_from_generated_file(*, path: Path) -> Result[DerivedBomLock, ReleaseError]:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as error:
        return Err(
            ReleaseError(
                kind="invalid_input",
                message=f"failed to read {path.name}",
                hint=str(error),
            )
        )

    pins = parse_native_ci_sdk_ini(text=text, source=path.name)
    if isinstance(pins, Err):
        return pins
    return _build_derived_lock(source=path.name, pins=pins.value)


def _load_native_ci_bom_from_platformio(*, path: Path) -> Result[DerivedBomLock, ReleaseError]:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as error:
        return Err(
            ReleaseError(
                kind="invalid_input",
                message=f"failed to read {path.name}",
                hint=str(error),
            )
        )

    cfg = configparser.ConfigParser(interpolation=None)
    try:
        cfg.read_string(text)
    except (configparser.Error, ValueError) as error:
        return Err(
            ReleaseError(
                kind="invalid_input",
                message=f"invalid {path.name}: {error}",
            )
        )

    section = "env:native_ci"
    if not cfg.has_section(section):
        return Err(
            ReleaseError(
                kind="invalid_input",
                message=f"missing [{section}] in {path.name}",
                hint=path.name,
            )
        )

    lib_deps_raw = cfg.get(section, "lib_deps", fallback="")
    if not lib_deps_raw.strip():
        return Err(
            ReleaseError(
                kind="invalid_input",
                message=f"missing {section}.lib_deps in {path.name}",
                hint=path.name,
            )
        )

    pins = parse_open_control_git_pins(lib_deps_raw=lib_deps_raw)
    return _build_derived_lock(source=path.name, pins=pins)


def _build_derived_lock(
    *, source: str, pins: dict[str, str]
) -> Result[DerivedBomLock, ReleaseError]:
    ordered = tuple(
        OcSdkPin(repo=repo, sha=pins[repo])
        for repo in OPEN_CONTROL_NATIVE_CI_REPOS
        if repo in pins
    )
    if not ordered:
        return Err(
            ReleaseError(
                kind="invalid_input",
                message=f"no OpenControl pins found in {source}",
                hint=source,
            )
        )
    return Ok(
        DerivedBomLock(
            source=source,
            pins=ordered,
            expected_repos=OPEN_CONTROL_NATIVE_CI_REPOS,
        )
    )
