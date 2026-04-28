from __future__ import annotations

from pathlib import Path

from pytest import MonkeyPatch

from ms.core.result import Err
from ms.services import unit_tests
from ms.services.unit_tests import UnitTestDependencyError


def test_load_test_dependency_pin_reads_manifest(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    manifest = tmp_path / "test_dependencies.toml"
    manifest.write_text(
        """
[unity]
version = "2.6.1"
url = "https://example.test/unity.zip"
sha256 = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
strip_components = 1
""".lstrip(),
        encoding="utf-8",
    )
    monkeypatch.setattr(unit_tests, "_TEST_DEPENDENCIES_PATH", manifest)

    result = unit_tests.load_test_dependency_pin("unity")

    assert not isinstance(result, Err)
    assert result.value.version == "2.6.1"
    assert result.value.url == "https://example.test/unity.zip"
    assert result.value.sha256 == "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
    assert result.value.strip_components == 1


def test_load_test_dependency_pin_rejects_invalid_manifest(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    manifest = tmp_path / "test_dependencies.toml"
    manifest.write_text(
        """
[unity]
version = "2.6.1"
url = "https://example.test/unity.zip"
sha256 = "not-a-sha"
strip_components = 1
""".lstrip(),
        encoding="utf-8",
    )
    monkeypatch.setattr(unit_tests, "_TEST_DEPENDENCIES_PATH", manifest)

    result = unit_tests.load_test_dependency_pin("unity")

    assert isinstance(result, Err)
    assert isinstance(result.error, UnitTestDependencyError)
    assert "invalid [unity] entry" in result.error.message
