import configparser
import os
import tempfile
from pathlib import Path

from ms.core.result import Err, Ok, Result
from ms.release.domain.open_control_models import (
    OPEN_CONTROL_BOM_REPOS,
    OPEN_CONTROL_NATIVE_CI_REPOS,
    OcSdkPin,
)
from ms.release.errors import ReleaseError
from ms.release.infra.open_control import (
    OC_SDK_LOCK_FILE,
    parse_oc_sdk_ini,
    parse_open_control_git_pins,
)

OC_NATIVE_SDK_FILE = "oc-native-sdk.ini"


def next_bom_version(current: str) -> str:
    parts = current.split(".")
    if len(parts) != 3 or any(not part.isdigit() for part in parts):
        raise ValueError(f"invalid BOM version: {current}")
    major, minor, patch = (int(part) for part in parts)
    return f"{major}.{minor}.{patch + 1}"


def render_oc_sdk_ini(*, version: str, pins: tuple[OcSdkPin, ...]) -> str:
    ordered = _ordered_pins(pins=pins, expected_repos=OPEN_CONTROL_BOM_REPOS)
    lines = [
        "; OpenControl SDK lock for MIDI Studio firmware builds.",
        ";",
        "; This file defines a compatibility set (BOM): a tested combination of OpenControl",
        "; repos pinned by commit SHA.",
        ";",
        "; Rules:",
        "; - Use commit SHAs (no floating refs like main).",
        "; - Bump oc_sdk.version when any pin changes.",
        "",
        "[oc_sdk]",
        f"version = {version}",
        "",
        "[oc_sdk_deps]",
        "lib_deps =",
    ]
    lines.extend(_render_lib_dep_lines(ordered))
    return "\n".join(lines) + "\n"


def write_oc_sdk_ini(
    *, core_root: Path, version: str, pins: tuple[OcSdkPin, ...]
) -> Result[Path, ReleaseError]:
    path = core_root / OC_SDK_LOCK_FILE
    rendered = render_oc_sdk_ini(version=version, pins=pins)
    write = _atomic_write_text(path=path, content=rendered)
    if isinstance(write, Err):
        return write

    verify = parse_oc_sdk_ini(text=rendered)
    if isinstance(verify, Err):
        return verify

    reparsed = parse_oc_sdk_ini(text=path.read_text(encoding="utf-8"))
    if isinstance(reparsed, Err):
        return reparsed

    expected = {
        pin.repo: pin.sha
        for pin in _ordered_pins(pins=pins, expected_repos=OPEN_CONTROL_BOM_REPOS)
    }
    actual = reparsed.value.pins_by_repo()
    if actual != expected or reparsed.value.version != version:
        return Err(
            ReleaseError(
                kind="invalid_input",
                message=f"post-write verification failed for {path.name}",
                hint=path.name,
            )
        )

    return Ok(path)


def render_native_ci_sdk_ini(*, pins: tuple[OcSdkPin, ...]) -> str:
    ordered = _ordered_pins(pins=pins, expected_repos=OPEN_CONTROL_NATIVE_CI_REPOS)
    lines = [
        "; Derived OpenControl BOM projection for native_ci.",
        "; Generated from oc-sdk.ini. Do not edit by hand.",
        "",
        "[oc_native_sdk_deps]",
        "lib_deps =",
    ]
    lines.extend(_render_lib_dep_lines(ordered))
    return "\n".join(lines) + "\n"


def write_native_ci_sdk_ini(
    *, core_root: Path, pins: tuple[OcSdkPin, ...]
) -> Result[Path, ReleaseError]:
    path = core_root / OC_NATIVE_SDK_FILE
    rendered = render_native_ci_sdk_ini(pins=pins)
    write = _atomic_write_text(path=path, content=rendered)
    if isinstance(write, Err):
        return write

    reparsed = parse_native_ci_sdk_ini(text=path.read_text(encoding="utf-8"), source=path.name)
    if isinstance(reparsed, Err):
        return reparsed

    expected = {
        pin.repo: pin.sha
        for pin in _ordered_pins(pins=pins, expected_repos=OPEN_CONTROL_NATIVE_CI_REPOS)
    }
    actual = reparsed.value
    if actual != expected:
        return Err(
            ReleaseError(
                kind="invalid_input",
                message=f"post-write verification failed for {path.name}",
                hint=path.name,
            )
        )

    return Ok(path)


def parse_native_ci_sdk_ini(
    *, text: str, source: str = OC_NATIVE_SDK_FILE
) -> Result[dict[str, str], ReleaseError]:
    cfg = configparser.ConfigParser(interpolation=None)
    try:
        cfg.read_string(text)
    except (configparser.Error, ValueError) as error:
        return Err(
            ReleaseError(
                kind="invalid_input",
                message=f"invalid {source}: {error}",
            )
        )

    if not cfg.has_section("oc_native_sdk_deps"):
        return Err(
            ReleaseError(
                kind="invalid_input",
                message=f"missing [oc_native_sdk_deps] in {source}",
                hint=source,
            )
        )

    lib_deps_raw = cfg.get("oc_native_sdk_deps", "lib_deps", fallback="")
    if not lib_deps_raw.strip():
        return Err(
            ReleaseError(
                kind="invalid_input",
                message=f"missing oc_native_sdk_deps.lib_deps in {source}",
                hint=source,
            )
        )

    pins = parse_open_control_git_pins(lib_deps_raw=lib_deps_raw)
    missing = [repo for repo in OPEN_CONTROL_NATIVE_CI_REPOS if repo not in pins]
    if missing:
        return Err(
            ReleaseError(
                kind="invalid_input",
                message=f"native_ci BOM missing pins: {', '.join(missing)}",
                hint=source,
            )
        )
    return Ok({repo: pins[repo] for repo in OPEN_CONTROL_NATIVE_CI_REPOS})


def _ordered_pins(
    *, pins: tuple[OcSdkPin, ...], expected_repos: tuple[str, ...]
) -> tuple[OcSdkPin, ...]:
    by_repo = {pin.repo: pin for pin in pins}
    missing = [repo for repo in expected_repos if repo not in by_repo]
    if missing:
        raise ValueError(f"missing OpenControl pins: {', '.join(missing)}")
    return tuple(by_repo[repo] for repo in expected_repos)


def _render_lib_dep_lines(pins: tuple[OcSdkPin, ...]) -> list[str]:
    return [
        f"    oc-{pin.repo}=https://github.com/open-control/{pin.repo}.git#{pin.sha}"
        for pin in pins
    ]


def _atomic_write_text(*, path: Path, content: str) -> Result[None, ReleaseError]:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            newline="\n",
            delete=False,
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
        ) as handle:
            handle.write(content)
            tmp_path = Path(handle.name)
        os.replace(tmp_path, path)
    except OSError as error:
        return Err(
            ReleaseError(
                kind="invalid_input",
                message=f"failed to write {path.name}",
                hint=str(error),
            )
        )
    return Ok(None)
