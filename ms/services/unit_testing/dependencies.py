from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from ms.core.hashing import is_sha256, sha256_file
from ms.core.result import Err, Ok, Result
from ms.core.workspace import Workspace
from ms.output.console import ConsoleProtocol, Style
from ms.platform.files import atomic_write_text
from ms.tools.download import Downloader
from ms.tools.http import RealHttpClient
from ms.tools.installer import Installer

from .models import UnitTestDependencyError, UnitTestError

_TEST_DEPENDENCIES_PATH = Path(__file__).resolve().parents[2] / "data" / "test_dependencies.toml"


@dataclass(frozen=True, slots=True)
class TestDependencyPin:
    name: str
    version: str
    url: str
    sha256: str
    strip_components: int


def load_test_dependency_pin(name: str) -> Result[TestDependencyPin, UnitTestError]:
    try:
        with open(_TEST_DEPENDENCIES_PATH, "rb") as f:
            data = tomllib.load(f)
    except OSError as e:
        return Err(
            UnitTestDependencyError(
                dependency=name,
                message=f"failed to read {_TEST_DEPENDENCIES_PATH}: {e}",
            )
        )
    except tomllib.TOMLDecodeError as e:
        return Err(
            UnitTestDependencyError(
                dependency=name,
                message=f"invalid TOML in {_TEST_DEPENDENCIES_PATH}: {e}",
            )
        )

    raw = data.get(name)
    if not isinstance(raw, dict):
        return Err(
            UnitTestDependencyError(
                dependency=name,
                message=f"missing [{name}] in {_TEST_DEPENDENCIES_PATH}",
            )
        )

    entry = cast("dict[str, object]", raw)
    version = entry.get("version")
    url = entry.get("url")
    digest = entry.get("sha256")
    strip_components = entry.get("strip_components", 0)
    if (
        not isinstance(version, str)
        or not isinstance(url, str)
        or not isinstance(digest, str)
        or not isinstance(strip_components, int)
        or not is_sha256(digest.lower())
    ):
        return Err(
            UnitTestDependencyError(
                dependency=name,
                message=f"invalid [{name}] entry in {_TEST_DEPENDENCIES_PATH}",
            )
        )

    return Ok(
        TestDependencyPin(
            name=name, version=version, url=url, sha256=digest.lower(),
            strip_components=strip_components,
        )
    )


def ensure_test_dependency(
    *, workspace: Workspace, console: ConsoleProtocol, name: str, dry_run: bool,
) -> Result[Path, UnitTestError]:
    pin = load_test_dependency_pin(name)
    if isinstance(pin, Err):
        return pin

    install_dir = workspace.cache_dir / "test-deps" / pin.value.name / pin.value.version
    expected_header = install_dir / "src" / "unity.h"
    expected_source = install_dir / "src" / "unity.c"
    marker = install_dir / ".ms-test-dependency"

    if dry_run:
        return Ok(install_dir)

    if (
        expected_header.exists()
        and expected_source.exists()
        and marker.exists()
        and marker.read_text(encoding="utf-8").strip() == pin.value.sha256
    ):
        return Ok(install_dir)

    downloader = Downloader(RealHttpClient(timeout=60.0), workspace.download_cache_dir)
    downloaded = downloader.download(pin.value.url)
    if isinstance(downloaded, Err):
        return Err(
            UnitTestDependencyError(
                dependency=name,
                message=str(downloaded.error),
                hint="Check network access or pre-populate the workspace download cache.",
            )
        )

    actual = sha256_file(downloaded.value.path)
    if actual != pin.value.sha256:
        downloader.clear_cache(pin.value.url)
        return Err(
            UnitTestDependencyError(
                dependency=name,
                message=(
                    f"checksum mismatch for {downloaded.value.path}: "
                    f"expected {pin.value.sha256}, got {actual}"
                ),
                hint=f"Review {_TEST_DEPENDENCIES_PATH}.",
            )
        )

    installed = Installer().install(
        downloaded.value.path, install_dir, strip_components=pin.value.strip_components,
    )
    if isinstance(installed, Err):
        return Err(
            UnitTestDependencyError(
                dependency=name, message=str(installed.error),
                hint="Remove the test dependency cache and retry.",
            )
        )

    if not expected_header.exists() or not expected_source.exists():
        return Err(
            UnitTestDependencyError(
                dependency=name,
                message=f"installed dependency is missing Unity sources in {install_dir}",
                hint=f"Review {_TEST_DEPENDENCIES_PATH}.",
            )
        )

    atomic_write_text(marker, f"{pin.value.sha256}\n", encoding="utf-8")
    console.print(f"{name}: test dependency ready", Style.DIM)
    return Ok(install_dir)
